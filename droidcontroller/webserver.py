import time
import threading
import sys
import traceback

try:
    if sys.version_info.major >= 3:
        import http.server as BaseHTTPServer
    else:
    #    from BaseHTTPServer import BaseHTTPRequestHandler,HTTPServer
        import BaseHTTPServer
except:
    import BaseHTTPServer

from os import curdir, sep
import os

from droidcontroller.indata import InData
from droidcontroller.indata_pacui import InDataPacui

gindata = None

class WebServer(threading.Thread):
    ''' Implement Web server for data API and basic home page
    '''

    def __init__(self, port=8080, indata=InData()):
        global gindata
        gindata = indata
        self.port = port
        self.ev = threading.Event()
        self.running = False
        self.thread = threading.Thread.__init__(self)
        print(BaseHTTPServer.BaseHTTPRequestHandler.__init__.__doc__)

    def run(self):
        ''' Webserver thread run() method
        '''
        self.running = True
        self.starttime = time.time()
#        self.httprequesthandler = self.myHTTPRequestHandler()
#        self.server = BaseHTTPServer.HTTPServer(('', self.port), self.httprequesthandler)
        self.server = BaseHTTPServer.HTTPServer(('', self.port), self.myHTTPRequestHandler)
        print('Started http server on port ' , self.port)
        self.server.serve_forever()
        while self.running:
            self.ev.wait(1000)

    def stop(self):
        ''' Stop webserver thread
        '''
        self.running = False
        self.ev.set()
        self.server.socket.close()

    #This class will handle any incoming request from the browser
    class myHTTPRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):

        def __init__(self, request, client_address, server):
            datadir='/root/d4c/webui' # ei saa default ette anda klassi defin?
            self.datadir=datadir
            BaseHTTPServer.BaseHTTPRequestHandler.__init__(self, request, client_address, server)

        #Handler for the GET requests
        def do_GET(self):
            #print("REQUEST: " + str(self)) # debug

            if self.path=="/":
                self.path="/webui.html"

            try:
                if self.path == "/pacui.json":
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    conv = InDataPacui(gindata)
                    try:
                        self.wfile.write(conv.getJSON().encode('utf-8'))
                    except: #  Exception, e: # problem with py3
                        print('problem with wfile') # self.wfile.write('error writing /pacui.json: ') # + str(e))
                        traceback.print_exc()
                    return

                if self.path == "/exit":
                    server.socket.close()

                #Check the file extension required and
                #set the right mime type
                sendReply = False
                if self.path.endswith(".html"):
                    mimetype='text/html'
                    sendReply = True
                if self.path.endswith(".jpg"):
                    mimetype='image/jpg'
                    sendReply = True
                if self.path.endswith(".gif"):
                    mimetype='image/gif'
                    sendReply = True
                if self.path.endswith(".js"):
                    mimetype='application/javascript'
                    sendReply = True
                if self.path.endswith(".css"):
                    mimetype='text/css'
                    sendReply = True
                if self.path.endswith(".json"):
                    mimetype='application/json'
                    sendReply = True

                if sendReply == True:
                    #Open the static file requested and send it
                    f = open(self.datadir + self.path)
                    self.send_response(200)
                    self.send_header('Content-type',mimetype)
                    self.end_headers()
                    try:
                        self.wfile.write(f.read().encode('utf-8')) # .encode('utf-8') works with py3
                        #self.wfile.write(f.read())
                    except: #  Exception, e: # py3 problem
                        traceback.print_exc()
                        #self.wfile.write('error writing ' + self.datadir + self.path) #  + ': ' + str(e)) # py3 problem
                    f.close()
                return

            except IOError:
                self.send_error(404,'File Not Found: %s %s' % (self.datadir, self.path))

