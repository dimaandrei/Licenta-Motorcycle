import io
import picamera
import logging
import socketserver
import pickle
import struct
import threading
from threading import Condition

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


class SingleTCPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        srcaddr, srcport = self.request.getpeername()
        print("Connection from {}:{}".format(srcaddr, srcport))

        # handler(self.request, fakeport)
        while True:
            with output.condition:
                output.condition.wait()
                frame = output.frame
                a = pickle.dumps(frame)
                message = struct.pack("Q",len(a))+a
                self.request.sendall(message)

class StreamingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, RequestHandlerClass):
        socketserver.TCPServer.__init__(self, server_address, RequestHandlerClass)

output = StreamingOutput()

def cameraThread():
    global output
    with picamera.PiCamera(resolution='640x480', framerate=24) as camera:
        #Uncomment the next line to change your Pi's Camera rotation (in degrees)
        camera.rotation = 180
        camera.start_recording(output, format='mjpeg')
        try:
            address = ('192.168.0.187', 10050)
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

