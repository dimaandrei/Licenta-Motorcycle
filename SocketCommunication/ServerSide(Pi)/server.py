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
from signal import signal, SIGINT
from sys import exit
import socket

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
    def __init__(self, arduino_comm_q, serial_port='/dev/serial0', baud_rate=9600):
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
                continue

            command = self.arduino_comm_q.get()
            print(command)
            if len(command) == 2:
                self.serial_comm.write(command)
            else:
                print("Something went wrong! Invalid command!")

    def terminate(self) -> None:
        self.run_flag=False
        super(SerialComm, self).terminate()


class SingleTCPHandler(socketserver.BaseRequestHandler):
    payload_size = struct.calcsize("B")

    def handle(self):
        try:
            srcaddr, srcport = self.request.getpeername()
            print("Connection from {}:{}".format(srcaddr, srcport))
            self.thread = threading.Thread(target=self.recieveData, args=[self.request])
            self.thread.start()
            while True:
                with output.condition:
                    output.condition.wait()
                    frame = output.frame
                    a = pickle.dumps(frame)
                    message = struct.pack("Q",len(a))+a
                    self.request.sendall(message)
        except socket.error as e:
            print(f'Socket exception! Probably client socket was closed!')
            # print(f'Errpr: {e}')

    def recieveData(self, request):
        self.recievingData = True
        data = b''
        try:
            while self.recievingData:
                print("Waiting for data: ", sep= '')
                while len(data) < self.payload_size:
                    packet = request.recv(128)
                    if not packet: break
                    data+=packet

                packed_msg_size = data[:self.payload_size]
                data = data[self.payload_size:]
                msg_size = struct.unpack("B",packed_msg_size)[0]

                while len(data) < msg_size:
                    data += request.recv(128)

                command = data[:msg_size]
                data = data[msg_size:]
                print(command)
                if commands_queue.full():
                    commands_queue.get_nowait()
                commands_queue.put(command)
        except socket.error as e:
            print(f'Socket exception! Probably client socket was closed!')
            # print(f'Errpr: {e}')


class StreamingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, RequestHandlerClass):
        socketserver.TCPServer.__init__(self, server_address, RequestHandlerClass)


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


output = StreamingOutput()
commands_queue = Queue()
event = Event()


def handler(signal_received, frame):
    event.set()

def main():
    signal(SIGINT, handler)
    camera_thread = threading.Thread(target=cameraThread)
    camera_thread.daemon = True
    camera_thread.start()
    print('Server loop running in thread: ', camera_thread.name)
    serial_comm = SerialComm(arduino_comm_q=commands_queue)
    serial_comm.start()

    while True:
        if event.is_set():
            print("Exiting all child processes..")
            serial_comm.terminate()
            commands_queue.close()
            # Terminating main process
            exit(0)

if __name__ == '__main__':
    main()

