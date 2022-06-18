
import serial
import time

<<<<<<< HEAD
ser = serial.Serial("/dev/serial0", 9600, timeout=1)

=======
#ser = serial.Serial("/dev/serial0", 115200, timeout=1)
ser = serial.Serial("/dev/ttyACM0", 9600, timeout=1)
>>>>>>> a349a54011a5c752d3aa353fc839785ac0d1f546
# Clear DTR, wait one second, flush input, then set DTR.

ser.setDTR(False)
time.sleep(1)
ser.flushInput()
ser.setDTR(True)
time.sleep(2)

if __name__ == '__main__':
    ser.reset_input_buffer()
    while True:
        #  if ser.in_waiting > 0:
<<<<<<< HEAD
        ser.write(b'\x02\x00')
        # line = ser.readline().decode('utf-8').rstrip()
        #print(line)
=======
        ser.write(b'\x01\x00')
        
>>>>>>> a349a54011a5c752d3aa353fc839785ac0d1f546
        time.sleep(1)

