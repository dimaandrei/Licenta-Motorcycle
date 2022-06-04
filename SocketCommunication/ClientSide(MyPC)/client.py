
import socket
import cv2
import pickle
import struct
import imutils
import numpy as np



if __name__ == '__main__':
    # Client socket
    # create an INET, streaming socket : 
    client_socket = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    host_ip = '192.168.0.187' # Pi's address
    port = 10050 

    # now connect to the web server on the specified port number
    client_socket.connect((host_ip,port)) 

    data = b''

    # Q: unsigned long long integer(8 bytes)
    payload_size = struct.calcsize("Q")


    while True:
        while len(data) < payload_size:
            packet = client_socket.recv(4*1024)
            if not packet: break
            data+=packet
        packed_msg_size = data[:payload_size]
        data = data[payload_size:]
        msg_size = struct.unpack("Q",packed_msg_size)[0]
        while len(data) < msg_size:
            data += client_socket.recv(4*1024)
        frame_data = data[:msg_size]
        data  = data[msg_size:]
        frame = pickle.loads(frame_data)
        nparr = np.frombuffer(frame, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        cv2.imshow("Receiving...",frame)
        key = cv2.waitKey(10) 
        if key  == 13:
            break
        
    client_socket.close()
