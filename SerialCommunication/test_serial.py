
import serial
import time

ser = serial.Serial("/dev/serial0", 9600, timeout=1)

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
        ser.write(b'\x02\x00')
        # line = ser.readline().decode('utf-8').rstrip()
        #print(line)
        time.sleep(1)

