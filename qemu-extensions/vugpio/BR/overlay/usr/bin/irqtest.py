#!/usr/bin/python
#!/usr/bin/python
import select
f=open("/sys/class/gpio/btn13/value","r")
e=select.epoll()
e.register(f,select.EPOLLPRI)
while True:
  print (f.read())
  e.poll()
  f.seek(0,0)
