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

import RPi.GPIO as GPIO
import time
 
# GPIO Mode (BOARD / BCM)
GPIO.setmode(GPIO.BCM)
 
GPIO_TRIGGER = 18
GPIO_ECHO = 24
 
GPIO.setup(GPIO_TRIGGER, GPIO.OUT)
GPIO.setup(GPIO_ECHO, GPIO.IN)

class StreamingOutput():
    def __init__(self):
        self.frame = None
        self.buffer = io.BytesIO()
        self.condition = Condition()

    def write(self, buf):
        if buf.startswith(b'\xff\xd8'):
            self.buffer.truncate()
            with self.condition:
                self.frame = self.buffer.getvalue()
                self.condition.notify_all()
            self.buffer.seek(0)
        return self.buffer.write(buf)


class SerialComm(Process):
    def __init__(self, arduinoCommQ, serial_port='/dev/serial0', baud_rate=9600):
        super(SerialComm, self).__init__()
        self.arduinoCommQ = arduinoCommQ
        self.serialComm = serial.Serial(serial_port, baud_rate, timeout=1)

        # Clear Data Terminal Ready, wait one second, flush input, then set it.

        self.serialComm.setDTR(False)
        time.sleep(1)
        self.serialComm.flushInput()
        self.serialComm.setDTR(True)
        time.sleep(2)
        self.runFlag=True
        
    def run(self) -> None:
        self.serialComm.reset_input_buffer()
        while self.runFlag:
            if self.arduinoCommQ.empty():
                continue

            command = self.arduinoCommQ.get()
            print(command)
            if len(command) == 2:
                self.serialComm.write(command)
            else:
                print("Something went wrong! Invalid command!")

    def terminate(self) -> None:
        print("\tExiting serial comm..")
        self.runFlag=False
        super(SerialComm, self).terminate()

class FrontObstacleDetector(Process):
    def __init__(self, arduinoCommQ):
        super(FrontObstacleDetector, self).__init__()
        self.arduinoCommQ = arduinoCommQ

        self.runFlag=True

    def run(self) -> None:
        print("Front obstacles detector activated!")
        startTime = time.time()
        stopTime = time.time()
        while self.runFlag:
            # set Trigger to HIGH
            GPIO.output(GPIO_TRIGGER, True)

            # set Trigger after 0.001ms to LOW
            time.sleep(0.000001)
            GPIO.output(GPIO_TRIGGER, False)

             # save StartTime
            while GPIO.input(GPIO_ECHO) == 0:
                startTime = time.time()

            # save time of arrival
            while GPIO.input(GPIO_ECHO) == 1:
                stopTime = time.time()

            # time difference between start and arrival
            timeElapsed = stopTime - startTime
            # multiply with the sonic speed (34300 cm/s)
            distance = timeElapsed * 34300 / 2
            print(distance)
            if distance < 25:
                print("Obstacle collision danger!")
                if commandsQueue.full():
                    commandsQueue.get_nowait()
                commandsQueue.put(b'\x02\x00')
            time.sleep(1)

    def terminate(self) -> None:
        self.runFlag=False
        print("\tExiting front obstacles detector..")
        super(FrontObstacleDetector, self).terminate()


class SingleTCPHandler(socketserver.BaseRequestHandler):
    payloadSize = struct.calcsize("B")
    recievingData = True
    def handle(self):
        try:
            srcaddr, srcport = self.request.getpeername()
            print("Connection from {}:{}".format(srcaddr, srcport))
            self.receiveDataThread = threading.Thread(target=self.receiveData, args=[self.request])
            self.receiveDataThread.start()
            while True:
                with output.condition:
                    output.condition.wait()
                    frame = output.frame
                    a = pickle.dumps(frame)
                    message = struct.pack("Q",len(a))+a
                    self.request.sendall(message)
        except socket.error as e:
            print(f'Socket exception! Probably client socket was closed! \nErr: {e}')
 
    def receiveData(self, request):
        data = b''
        try:
            while self.recievingData:
                print("Waiting for data: ", sep= '')
                while len(data) < self.payloadSize:
                    packet = request.recv(128)
                    if not packet: break
                    data+=packet

                packedMsgSize = data[:self.payloadSize]
                data = data[self.payloadSize:]
                msgSize = struct.unpack("B",packedMsgSize)[0]

                while len(data) < msgSize:
                    data += request.recv(128)

                command = data[:msgSize]
                data = data[msgSize:]

                if command ==  b'\x04\x01':
                    detectFrontObstaclesEvent.set()
                elif command ==  b'\x04\x00':
                    detectFrontObstaclesEvent.clear()

                if commandsQueue.full():
                    commandsQueue.get_nowait()
                commandsQueue.put(command)
        except socket.error as e:
            print(f'Socket exception! Probably client socket was closed! \nErr:{e}')
            
    def finish(self) -> None:
        self.recievingData = False
        return super().finish()


class StreamingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, RequestHandlerClass):
        socketserver.TCPServer.__init__(self, server_address, RequestHandlerClass)


def cameraStreamingThread():
    global output
    with picamera.PiCamera(resolution='160x128', framerate=24) as camera:
        camera.rotation = 180
        camera.start_recording(output, format='mjpeg')
        try:
            # address = ('192.168.32.161', 10050)# phone
            address = ('192.168.0.187', 10050) # home
            # address = ('192.168.0.139', 10050) PI4

            server = StreamingServer(address, SingleTCPHandler)
            server.serve_forever()
        finally:
            camera.stop_recording()
            server.shutdown()


output = StreamingOutput()
commandsQueue = Queue()
closeEvent = Event()
detectFrontObstaclesEvent = Event() # to activate

def handler(signal_received, frame):
    closeEvent.set()

def main():
    signal(SIGINT, handler)
    cameraThread = threading.Thread(target=cameraStreamingThread)
    cameraThread.daemon = True
    cameraThread.start()
    print('Server loop running in thread: ', cameraThread.name)
    serialComm = SerialComm(arduinoCommQ=commandsQueue)
    serialComm.start()

    frontObstacleDetectorProcess = None

    try:
        while True:
            if detectFrontObstaclesEvent.is_set() and frontObstacleDetectorProcess is None:
                frontObstacleDetectorProcess = FrontObstacleDetector(arduinoCommQ=commandsQueue)
                frontObstacleDetectorProcess.start()
            
            elif frontObstacleDetectorProcess is not None and not detectFrontObstaclesEvent.is_set():
                frontObstacleDetectorProcess.terminate()
                frontObstacleDetectorProcess = None

            if closeEvent.is_set():
                break
    finally:
        print("Exiting all child processes..")
        serialComm.terminate()
        if frontObstacleDetectorProcess is not None and frontObstacleDetectorProcess.is_alive():
            frontObstacleDetectorProcess.terminate()
        commandsQueue.close()
        GPIO.cleanup()
    exit(0)


if __name__ == '__main__':
    main()

