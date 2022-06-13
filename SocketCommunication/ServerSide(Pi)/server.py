import io
import picamera
import logging
import socketserver
import pickle
import struct
import threading
import serial
import time
from threading import Condition
from multiprocessing import Process, Queue, Event

class StreamingOutput():
    def __init__(self):
        self.frame = None
        self.buffer = io.BytesIO()
        self.condition = Condition()

    def write(self, buf):
        if buf.startswith(b'\xff\xd8'):
            # New frame, copy the existing buffer's content and notify all
            # clients it's available
            self.buffer.truncate()
            with self.condition:
                self.frame = self.buffer.getvalue()
                self.condition.notify_all()
            self.buffer.seek(0)
        return self.buffer.write(buf)


class SerialComm(Process):
    def __init__(self, arduino_comm_q, serial_port='/dev/serial0', baud_rate =115200):
        super(SerialComm, self).__init__()
        self.arduino_comm_q = arduino_comm_q
        self.serial_comm = serial.Serial(serial_port, baud_rate, timeout=1)

        # Clear DTR, wait one second, flush input, then set DTR.

        self.serial_comm.setDTR(False)
        time.sleep(1)
        self.serial_comm.flushInput()
        self.serial_comm.setDTR(True)
        time.sleep(2)
        self.run_flag=True
        
    def run(self) -> None:
        self.serial_comm.reset_input_buffer()
        while self.run_flag:
            if self.arduino_comm_q.empty():
                pass
            
            command = self.arduino_comm_q.get()
            if command == 'stop':
                pass
                self.serial_comm.write(b"Hello from Raspberry Pi!\n")
            elif command == 'max-30km/h':
                pass
                self.serial_comm.write(b"Hello from Raspberry Pi!\n")
            elif command == 'max-70km/h':
                pass
                self.serial_comm.write(b"Hello from Raspberry Pi!\n")
            elif command == 'turn-right-ahead':
                pass
                self.serial_comm.write(b"Hello from Raspberry Pi!\n")
            elif command == 'turn-left-ahead':
                pass
                self.serial_comm.write(b"Hello from Raspberry Pi!\n")
            else:
                print("Unknown command!")


    def terminate(self) -> None:
        self.run_flag=False
        super(SerialComm, self).terminate()



class SingleTCPHandler(socketserver.BaseRequestHandler):
    payload_size = struct.calcsize("Q")

    def handle(self):
        srcaddr, srcport = self.request.getpeername()
        print("Connection from {}:{}".format(srcaddr, srcport))
        self.thread = threading.Thread(target=self.recieveData, args=[self.request])
        self.thread.start()
        # handler(self.request, fakeport)
        while True:
            with output.condition:
                output.condition.wait()
                frame = output.frame
                a = pickle.dumps(frame)
                message = struct.pack("Q",len(a))+a
                self.request.sendall(message)

    def recieveData(self, request):
        self.recievingData = True
        data = b''

        while self.recievingData:
            print("Waiting for data")
            while len(data) < self.payload_size:
                packet = request.recv(256)
                if not packet: break
                data+=packet

            packed_msg_size = data[:self.payload_size]
            data = data[self.payload_size:]
            msg_size = struct.unpack("Q",packed_msg_size)[0]

            while len(data) < msg_size:
                data += request.recv(256)

            command = data[:msg_size]
            data = data[msg_size:]
            print(command)


class StreamingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, RequestHandlerClass):
        socketserver.TCPServer.__init__(self, server_address, RequestHandlerClass)

output = StreamingOutput()

def cameraThread():
    global output
    with picamera.PiCamera(resolution='320x256', framerate=24) as camera:
        #Uncomment the next line to change your Pi's Camera rotation (in degrees)
        camera.rotation = 180
        camera.start_recording(output, format='mjpeg')
        try:
            address = ('192.168.0.187', 10050)
            #address = ('192.168.0.139', 10050)
            server = StreamingServer(address, SingleTCPHandler)
            server.serve_forever()
        finally:
            camera.stop_recording()
            server.shutdown()
            print("here")


def main():
    camera_thread = threading.Thread(target=cameraThread)
    camera_thread.daemon = True
    camera_thread.start()
    print('Server loop running in thread: ', camera_thread.name)
    while 1:
        pass

if __name__ == '__main__':
    main()

