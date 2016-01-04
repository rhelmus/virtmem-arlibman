import datetime
import serial
import struct
import sys
import threading
import time

class Commands:
    init, initPool, read, write, inputAvailable, inputRequest, inputPeek, ping = range(0, 8)

class State:
    initialized = False
    processState = 'idle'
    initValue, memoryPool = None, None
    inputData = bytearray()
    inputLock = threading.Lock()
    doQuit = False
    outdev = None

serInterface = serial.Serial()

def blockedRead(size):
    ret = bytearray()
    while size > 0:
        bytes = serInterface.read(size)
        if bytes:
            ret += bytes
            size -= len(bytes)
    return ret

def readInt():
    return struct.unpack('i', blockedRead(4))[0]

def writeInt(i):
    serInterface.write(struct.pack('i', i))

def sendCommand(cmd):
    serInterface.write(bytes([State.initValue]))
    serInterface.write(bytes([cmd]))
    #print("send: ", bytes([State.initValue]), "/", bytes([cmd]))

def processByte(byte, printunknown=True):
    val = ord(byte)
    if State.processState == 'gotinit':
        handleCommand(val)
        State.processState = 'idle'
    elif val == State.initValue:
        assert(State.processState == 'idle')
#        print("Got init!")
        State.processState = 'gotinit'
    else:
        assert(State.processState == 'idle')
        if printunknown:
#            State.outdev.write(byte.decode('ascii', errors='ignore'))
            State.outdev.write(byte)
            State.outdev.flush()

def handleCommand(command):
    #print("command: ", command)
    if command == Commands.ping:
        sendCommand(Commands.ping)
    elif command == Commands.init:
        State.initialized = True
        State.memoryPool = None # remove pool
        sendCommand(Commands.init) # reply
    elif not State.initialized:
        pass
    elif command == Commands.initPool:
        State.memoryPool = bytearray(readInt())
        print("set memory pool:", len(State.memoryPool), flush=True)
    elif command == Commands.inputAvailable:
        with State.inputLock:
            writeInt(len(State.inputData))
            #print("request count: ", len(State.inputData))
    elif command == Commands.inputRequest:
        with State.inputLock:
            count = min(readInt(), len(State.inputData))
            writeInt(count)
            #print("Input request: {} ({})".format(State.inputData[:count], count), flush=True)
            serInterface.write(State.inputData[:count])
            del State.inputData[:count]
    elif command == Commands.inputPeek:
        if len(State.inputData) == 0:
            serInterface.write(0)
        else:
            with State.inputLock:
                serInterface.write(1)
                serInterface.write(State.inputData[0])
    elif State.memoryPool == None:
        print("WARNING: tried to read/write unitialized memory pool")
    elif command == Commands.read:
        index, size = readInt(), readInt()
        serInterface.write(State.memoryPool[index:size+index])
#        print("read memPool: ", State.memoryPool[index:size+index])
#        print("read memPool: ", index, size)
    elif command == Commands.write:
        index, size = readInt(), readInt()
        State.memoryPool[index:size+index] = blockedRead(size)
#        print("write memPool: ", State.memoryPool)
#        print("write memPool: ", index, size)

def ensureConnection():
    print("Waiting until port {} can be opened...\n".format(serInterface.port))
    while not State.doQuit:
        try:
            serInterface.open()
            break
        except OSError:
            time.sleep(0.5)

    if State.doQuit:
        return

    time.sleep(1) # wait to settle after open (only needed if board resets)

    print("Connected and initialized!")

def connect(port, baud, initval, outdev):
    serInterface.port = port
    serInterface.baudrate = baud
    serInterface.timeout = 0

    State.initValue = initval
    State.outdev = outdev

    ensureConnection()

def update():
    global serInterface

    try:
        byte = serInterface.read(1)
        while byte:
            processByte(byte)
            byte = serInterface.read(1)
    # NOTE: catch for TypeError as workaround for indexing bug in PySerial
    except (serial.serialutil.SerialException, TypeError):
        print("Caught serial exception, port disconnected?")
        State.initialized = False
        p, b = serInterface.port, serInterface.baudrate
        serInterface.close()
        serInterface = serial.Serial()
        connect(p, b, State.initValue, State.outdev)

def processInput(line):
    #print("Sending input line:", line, flush=True)
    with State.inputLock:
        State.inputData += line

def quit():
    State.doQuit = True
