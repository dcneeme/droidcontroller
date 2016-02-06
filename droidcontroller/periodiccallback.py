import tornado.ioloop

class PeriodicCallback(tornado.ioloop.PeriodicCallback):
    ''' Use this to add a method to run/start callback immediately into PeriodicCallback class. '''
    def run_now(self):
        self.stop()
        #self._running = True
        try:
            return self.callback()
        except Exception:
            self.io_loop.handle_callback_exception(self.callback)
        finally:
            self.start()