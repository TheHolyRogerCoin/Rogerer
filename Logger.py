import Config, Irc
import md5, random, os, datetime, pytz, logging, time
from shutil import copyfile
from logging.handlers import TimedRotatingFileHandler


logger = logging.getLogger("Rotating Log")
logger.setLevel(logging.INFO)

if not os.path.exists(Config.config["logfile"]):
	with open(Config.config["logfile"],'w+'): pass

handler = TimedRotatingFileHandler(
	Config.config["logfile"],
	when="h",
	interval=24,
	backupCount=14)
logger.addHandler(handler)

def log(spec, text):
# Error Raw Connection Tx Whois Manager
	template = "erctwm"
	specifier = ""
	indent = ""
	pid = os.getpid()
	for c in template:
		specifier += c if c in spec else "_"
		if "r" in spec:
			indent = "  "
	with open(Config.config["logfile"], "a") as f:
		# t = time.time()
		for line in text.split("\n"):
			# f.write("[%s] [%s] [%f] <%s> %s\n" % (time.ctime(t), pid, t, specifier, line))
			# f.write("[%s] [%s] <%s> %s%s\n" % (datetime.datetime.now(pytz.timezone(Config.config["timezone"])).strftime('%d/%m/%y %H:%M:%S'), pid, specifier, indent, line))
			printLine = "[%s] [%s] <%s> %s%s\n" % (datetime.datetime.now(pytz.timezone(Config.config["timezone"])).strftime('%d/%m/%y %H:%M:%S'), pid, specifier, indent, line)
			if "e" in spec:
				logger.exception(printLine)
			elif "w" in spec:
				logger.warning(printLine)
			else:
				logger.info(printLine)

def clearlog():
	copyfile(Config.config["logfile"],"%s.bak" % (Config.config["logfile"]))
	with open(Config.config["logfile"],'w'): pass
	return

def irclog(text):
	if Config.config.get("irclog", None):
		for i in xrange(0, len(text), 350):
			# logger.info("[%s] IRCLOG: %s\n" % (datetime.datetime.now(pytz.timezone(Config.config["timezone"])).strftime('%d/%m/%y %H:%M:%S'), pid, specifier, text[i:i+350]))
			Irc.instance_send(Config.config["irclog"][0], ("PRIVMSG", Config.config["irclog"][1], text[i:i+350]), priority = 0)

def token():
	m = md5.new()
	t = random.random()
	m.update(str(t))
	return m.hexdigest()[:8]
