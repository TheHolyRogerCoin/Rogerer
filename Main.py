import socket, errno, time, sys, traceback, threading
sys.dont_write_bytecode = True
import Global, Config, Irc, Logger

Logger.log("m", "Started Rogerer")
for instance in Config.config["instances"]:
	Global.manager_queue.put(("Spawn", instance))
Global.manager_queue.put(("Signal",))
Irc.manager()
Logger.log("me", "Manager returned")
