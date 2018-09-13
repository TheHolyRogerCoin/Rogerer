import Config, Irc
import time, md5, random, os

def log(spec, text):
# Error Raw Connection Tx Whois Manager
	template = "erctwm"
	specifier = ""
	pid = os.getpid()
	for c in template:
		specifier += c if c in spec else "_"
	with open(Config.config["logfile"], "a") as f:
		t = time.time()
		for line in text.split("\n"):
			f.write("[%s] [%s] [%f] <%s> %s\n" % (time.ctime(t), pid, t, specifier, line))

def clearlog(spec, text):
	with open(Config.config["logfile"],'w'): pass

def irclog(text):
	if Config.config.get("irclog", None):
		for i in xrange(0, len(text), 350):
			Irc.instance_send(Config.config["irclog"][0], ("PRIVMSG", Config.config["irclog"][1], text[i:i+350]), priority = 0)

def token():
	m = md5.new()
	t = random.random()
	m.update(str(t))
	return m.hexdigest()[:8]
