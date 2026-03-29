#!/bin/sh

BINARIES_DIR="${0%/*}/"
# shellcheck disable=SC2164
cd "${BINARIES_DIR}"

mode_serial=false
mode_sys_qemu=false
while [ "$1" ]; do
    case "$1" in
    --serial-only|serial-only) mode_serial=true; shift;;
    --use-system-qemu) mode_sys_qemu=true; shift;;
    --) shift; break;;
    *) echo "unknown option: $1" >&2; exit 1;;
    esac
done

if ${mode_serial}; then
    EXTRA_ARGS='-nographic'
else
    EXTRA_ARGS=''
fi

if ! ${mode_sys_qemu}; then
    export PATH="/home/wzab/BR/buildroot-2025.11.2/output/host/bin:${PATH}"
fi

exec qemu-system-aarch64 -M virt,memory-backend=mem -cpu cortex-a53 -nographic -smp 1 -kernel Image -append "rootwait root=/dev/vda console=ttyAMA0" -netdev user,id=eth0 -device virtio-net-device,netdev=eth0 -drive file=rootfs.ext4,if=none,format=raw,id=hd0 -device virtio-blk-device,drive=hd0 \
-object memory-backend-memfd,id=mem,size=512M,share=on \
-chardev socket,id=gpio,path=/tmp/gpio.sock \
-device vhost-user-gpio-pci,chardev=gpio \
${EXTRA_ARGS} "$@"
