# vugpio (Virtio GPIO Userspace Backend)

A userspace implementation of a Virtio GPIO backend compatible with Linux guests using the gpio-virtio driver.

## Features

- Virtio GPIO device (request + event queues)
- Input/output GPIO lines
- Edge-triggered interrupts (rising, falling, both)
- Compatible with libgpiod tools (gpiomon, gpioset, gpioget)
- Optional control socket for external interaction
- Adjustable logging (--verbose, --quiet, --log-level)

## Requirements

- Python 3.8+
- QEMU with Virtio support
- Linux guest with gpio-virtio driver and libgpiod (the BR subdirectory contains information for building a dedicated Linux image)

## Running the Backend

Basic usage:

    python3 vugpio.py

With explicit socket paths:


    python3 vugpio.py \
      --socket-path /tmp/gpio.sock \
      --control-socket /tmp/gpio-gui.sock

    python3 gui3.py --control-socket /tmp/gpio-gui.sock

Logging options:

    --verbose
    --quiet
    --log-level warning

## Running QEMU

Example:

    qemu-system-aarch64 \
      -machine virt \
      -kernel Image \
      -append "root=/dev/vda console=ttyAMA0" \
      -drive file=rootfs.ext4,format=raw,if=virtio \
      -chardev socket,id=gpio,path=/tmp/gpio.sock \
      -device vhost-user-gpio-pci,chardev=gpio \
      -nographic

## Inside the Guest

    modprobe gpio-virtio
    gpiodetect
    gpioinfo
    gpioget gpiochip0 14
    gpioset gpiochip0 27=1
    gpiomon gpiochip0 14

## Control Socket

If enabled, allows external tools to inject GPIO values and trigger interrupts.

## Acknowledgements

This project was inspired by the Rust-VMM (https://github.com/rust-vmm) ecosystem and vhost-user backend implementations.

The design was based on the Virtio specification and existing implementations,
but the code itself is an independent Python implementation.

No code from Rust-VMM or other projects has been copied.

## License

The project was developed by Wojciech M. Zabolotny with significant
help from ChatGPT.

This project is released under the CC0-1.0 Universal license.
