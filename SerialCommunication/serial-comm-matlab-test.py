
import serial

import time


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    s = serial.Serial('COM7', 9600)
    while 1:
        s.write(b'\x01\x00')
        n = s.write(b'\x02\x6c')
        print(n)
        time.sleep(1)
# See PyCharm help at https://www.jetbrains.com/help/pycharm/
