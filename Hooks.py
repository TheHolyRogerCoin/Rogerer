# coding=utf8
import traceback, sys, re, time, datetime, pytz, threading, Queue, socket, subprocess

import Irc, Config, Transactions, Commands, Games, Config, Global, Logger, Expire

hooks = {}

def end_of_motd(instance, *_):
	Global.instances[instance].can_send.set()
	Logger.log("c", instance + ": End of motd, joining " + " ".join(Config.config["instances"][instance]))
	for channel in Config.config["instances"][instance]:
		Irc.instance_send(instance, ("JOIN", channel))
hooks["376"] = end_of_motd

def ping(instance, source, *args):
	Irc.instance_send(instance, tuple(("PONG",) + args), priority = 0, lock = False)
hooks["PING"] = ping

class Request(object):
	def __init__(self, instance, target, source, altnick, text, cmd):
		self.instance = instance
		self.target = target
		self.source = source
		self.nick = Irc.get_nickname(source, text)
		self.altnick = altnick
		self.text = text
		self.cmdalias = cmd

	def privmsg(self, targ, text, priority = None):
		Logger.log("c", self.instance + ": %s <- (pri=%s) %s " % (targ, str(priority),  text))
		for i in xrange(0, len(text), 350):
			if priority:
				Irc.instance_send(self.instance, ("PRIVMSG", targ, text[i:i+350]), priority = priority)
			else:
				Irc.instance_send(self.instance, ("PRIVMSG", targ, text[i:i+350]))

	def noticemsg(self, targ, text, priority = None):
		Logger.log("c", self.instance + " (NOTICE): %s <- (pri=%s) %s " % (targ, str(priority),  text))
		for i in xrange(0, len(text), 350):
			if priority:
				Irc.instance_send(self.instance, ("NOTICE", targ, text[i:i+350]), priority = priority)
			else:
				Irc.instance_send(self.instance, ("NOTICE", targ, text[i:i+350]))

	def reply(self, text, altnick = False):
		if self.nick == self.target:
			self.privmsg(self.target, self.nick + ": " + text, priority = 10)
		elif altnick:
			self.privmsg(self.target, self.altnick + ": " + text)
		else:
			self.privmsg(self.target, self.nick + ": " + text)

	def reply_private(self, text):
		self.privmsg(self.nick, self.nick + ": " + text, priority = 10)

	def notice_private(self, text):
		self.noticemsg(self.nick, self.nick + ": " + text, priority = 10)

	def say(self, text):
		if self.nick == self.target:
			self.privmsg(self.target, text, priority = 10)
		else:
			self.privmsg(self.target, text)

class FakeRequest(Request):
	def __init__(self, req, target, text):
		self.instance = req.instance
		self.target = req.target
		self.source = req.source
		self.nick = target
		self.text = text
		self.realnick = req.nick

	def privmsg(self, targ, text, priority = None):
		Logger.log("c", self.instance + ": %s <- %s " % (targ, text))
		for i in xrange(0, len(text), 350):
			if priority:
				Irc.instance_send(self.instance, ("PRIVMSG", targ, text[i:i+350]), priority = priority)
			else:
				Irc.instance_send(self.instance, ("PRIVMSG", targ, text[i:i+350]))

	def reply(self, text):
		self.privmsg(self.target, self.realnick + " [reply] : " + text)

	def reply_private(self, text):
		self.privmsg(self.target, self.realnick + " [reply_private]: " + text)

	def say(self, text):
		self.privmsg(self.target, text)

def run_command(cmd, req, arg):
	try:
		cmd(req, arg)
	except Exception as e:
		req.reply(repr(e))
		type, value, tb = sys.exc_info()
		Logger.log("ce", "ERROR in " + req.instance + " : " + req.text)
		Logger.log("ce", repr(e))
		Logger.log("ce", "".join(traceback.format_tb(tb)))
		Logger.irclog("Error while executing '%s' from '%s': %s" % (req.text, req.nick, repr(e)))
		Logger.irclog("".join(traceback.format_tb(tb)).replace("\n", " || "))
		del tb

def message(instance, source, target, text):
	host = Irc.get_host(source)
	text = Irc.strip_colours(text)
	if text == "\x01VERSION\x01":
		p = subprocess.Popen(["git", "rev-parse", "HEAD"], stdout = subprocess.PIPE)
		hash, _ = p.communicate()
		hash = hash.strip()
		p = subprocess.Popen(["git", "diff", "--quiet"])
		changes = p.wait()
		if changes:
			hash += "[+]"
		version = "Rogerer by TheHoliestRoger, version " + hash
		Irc.instance_send(instance, ("NOTICE", Irc.get_nickname(source, text), "\x01VERSION " + version + "\x01"), priority = 20)
	else:
		commandline = None
		altnick = Irc.get_nickname(source, text, altnick=True)
		if any(x.lower() in str(source).lower() for x in Config.config["bridgebotnicks"]) and ">" in str(text):
			text = text.split("> ", 1)[1]
		nick = Irc.get_nickname(source, text)
		if target == instance:
			commandline = text
		if len(text) > 1 and text[0] == Config.config["prefix"]:
			commandline = text[1:]
		elif (	len(Global.response_read_timers) > 0 and
				(target != instance or Irc.is_super_admin(source)) and (
					nick in Global.response_read_timers or 
					("@roger_that" in Global.response_read_timers and target in Config.config["welcome_channels"]))):
			if nick not in Global.response_read_timers and "@roger_that" in Global.response_read_timers:
				theReadTimer = "@roger_that"
				auto_or_text = text
				time_multiplier = (60*60)
			else:
				theReadTimer = nick
				auto_or_text = "auto"
				time_multiplier = (60)
			t = time.time()
			if Global.response_read_timers[theReadTimer]["time"] + 40 > t:
				commandline = "%s %s" % (Global.response_read_timers[theReadTimer]["cmd"], text)
			elif Global.response_read_timers[theReadTimer]["time"] + (10*time_multiplier) > t:
				commandline = "%s %s" % (Global.response_read_timers[theReadTimer]["cmd"], auto_or_text)
				Logger.log("c", "%s: timer expired (auto) for: %s on: %s, cmd: %s" % (
					instance, nick, theReadTimer, Global.response_read_timers[theReadTimer]["cmd"]))
			else:
				commandline = "%s end-game" % (Global.response_read_timers[theReadTimer]["cmd"])
				Logger.log("c", "%s: timer expired (ended) for: %s on: %s, cmd: %s" % (
					instance, nick, theReadTimer, Global.response_read_timers[theReadTimer]["cmd"]))
		# Track & update last time user talked in channel (ignore PM to bot for activity purposes)
		if target.startswith('#'):
			with Global.active_lock:
				if not target in Global.active_list.keys():
					Global.active_list[target] = {}
				Global.active_list[target][nick] = time.time()
		if commandline:
			if Irc.is_ignored(host) and not Irc.is_super_admin(source):
				Logger.log("c", instance + ": %s <%s ignored> %s " % (target, nick, text))
				return
			Logger.log("c", instance + ": %s <%s> %s " % (target, nick, text))
			if Config.config.get("ignore", None):
				t = time.time()
				score = Global.flood_score.get(host, (t, 0))
				score = max(score[1] + score[0] - t, 0) + Config.config["ignore"]["cost"]
				if score > Config.config["ignore"]["limit"] and not Irc.is_admin(source):
					Logger.log("c", instance + ": Ignoring " + host)
					Irc.ignore(host, Config.config["ignore"]["timeout"])
					Irc.instance_send(instance, ("PRIVMSG", nick, "You're sending commands too quickly. Your host is ignored for 240 seconds"))
					return
				Global.flood_score[host] = (t, score)
			src = nick
			if target == instance:
				reply = src
			else:
				reply = target
			commandline = commandline.rstrip(" \t")
			if commandline.find(" ") == -1:
				command = commandline
				args = []
			else:
				command, args = commandline.split(" ", 1)
				args = [a for a in args.split(" ") if len(a) > 0]
			if command[0] != '_':
				cmd = Commands.commands.get(command.lower(), None)
				if cmd == None:
					cmd = Games.games.get(command.lower(), None)
				if not cmd.__doc__ or cmd.__doc__.find("admin") == -1 or Irc.is_admin(source):
					if cmd:
						req = Request(instance, reply, source, altnick, commandline, command.lower())
						t = threading.Thread(target = run_command, args = (cmd, req, args))
						t.start()
hooks["PRIVMSG"] = message

def date_timestamp(date):
    dt = datetime.datetime.strptime(date, "%b %d %H:%M:%S %Y").replace(tzinfo = pytz.utc)
    epoch = datetime.datetime(1970, 1, 1, tzinfo=pytz.utc)
    return (dt - epoch).total_seconds()

def notice(instance, source, target, text):
	if "@" in source and Irc.get_host(source) == "services." and Irc.get_nickname(source, "") == "NickServ":
		m = re.match("Information on (\\S*) \\(account (\\S*)\\):", text)
		if m:
			Global.svsdata = {"nick": m.group(1), "account": m.group(2)}
			return
		m = re.match("(\\S*) is not registered\\.", text)
		if m:
			Global.svsdata = None
			Expire.svsdata({"nick": m.group(1)})
			return
		if Global.svsdata != None:
			m = re.match("Registered : ([^(]*) \\([^)]* ago\\)", text)
			if m:
				Global.svsdata["reg"] = int(date_timestamp(m.group(1)))
				return
			m = re.match("User Reg\\.  : ([^(]*) \\([^)]* ago\\)", text)
			if m:
				Global.svsdata["userreg"] = int(date_timestamp(m.group(1)))
				return
			m = re.match("Last seen  : ([^(]*) \\([^)]* ago\\)", text)
			if m:
				Global.svsdata["last"] = int(date_timestamp(m.group(1)))
				return
			m = re.match("Last seen  : now", text)
			if m:
				Global.svsdata["last"] = int(time.time())
				return
			m = re.match("Last seen  : \\(about (\\d*) weeks ago\\)", text)
			if m:
				Global.svsdata["lastweeks"] = int(m.group(1))
				return
			m = re.match("User seen  : ([^(]*) \\([^)]* ago\\)", text)
			if m:
				Global.svsdata["userlast"] = int(date_timestamp(m.group(1)))
				return
			m = re.match("User seen  : now", text)
			if m:
				Global.svsdata["userlast"] = int(time.time())
				return
			m = re.match("User seen  : \\(about (\\d*) weeks ago\\)", text)
			if m:
				Global.svsdata["userlastweeks"] = int(m.group(1))
				return
			m = re.match("\\*\\*\\* End of Info \\*\\*\\*", text)
			if m:
				Expire.svsdata(Global.svsdata)
				Global.svsdata = None
				return
hooks["NOTICE"] = notice

def join(instance, source, channel, account, _):
	curtime = time.time()
	if account == "*":
		account = False
	nick = Irc.get_nickname(source, "")
	with Global.account_lock:
		if nick  == instance:
			Global.account_cache[channel] = {}
		Global.account_cache[channel][nick] = account
		Global.nick_source_cache[nick] = source
		if account != False and account != None:
			Global.acctnick_list[account] = nick
		for channel in Global.account_cache:
			if nick in Global.account_cache[channel] and channel[0] != "@":
				if channel in Config.config["welcome_channels"] and (not account or not Transactions.check_exists(account)) and not Transactions.check_exists(nick) and (nick not in Global.welcome_list or Global.welcome_list[nick] + (60*10) < curtime):
					Global.welcome_list[nick] = curtime
					# Irc.instance_send(instance, ("PRIVMSG", channel, "Welcome our newest Rogeteer - %s! Try &help, &rogerme and &faucet to get started!" % (nick)), priority = 20, lock = False)
					Irc.instance_send(instance, ("PRIVMSG", channel, "Welcome our newest Rogeteer - %s! Try &help, &rogerme and &faucet to get started!" % (nick)), priority = 20, lock = False)
				elif channel in Config.config["welcome_channels"] and account and (Transactions.check_exists(nick) or Transactions.check_exists(account)) and (nick not in Global.welcome_list or Global.welcome_list[nick] + (60*10) < curtime):
					Global.welcome_list[nick] = curtime
					welcome_str = str(Commands.random_line('quotes_welcome'))
					Irc.instance_send(instance, ("NOTICE", nick, "Welcome back %s! %s" % (nick, welcome_str)), priority = 20, lock = False)
				Global.account_cache[channel][nick] = account
				Logger.log("w", "Propagating %s=%s into %s" % (nick, account, channel))
	if account != False:
		Expire.bump_last(account)
hooks["JOIN"] = join

def part(instance, source, channel, *_):
	nick = Irc.get_nickname(source, "")
	account = None
	with Global.account_lock:
		if nick == instance:
			del Global.account_cache[channel]
			Logger.log("w", "Removing cache for " + channel)
			return
		if nick in Global.account_cache[channel]:
			account = Global.account_cache[channel][nick]
		if nick in Global.account_cache[channel]:
			del Global.account_cache[channel][nick]
			Logger.log("w", "Removing %s from %s" % (nick, channel))
	if account != None and account != False:
		Expire.bump_last(account)
hooks["PART"] = part

def kick(instance, _, channel, nick, *__):
	account = None
	with Global.account_lock:
		if nick == instance:
			del Global.account_cache[channel]
			Logger.log("w", "Removing cache for " + channel)
			return
		if nick in Global.account_cache[channel]:
			account = Global.account_cache[channel][nick]
		if nick in Global.account_cache[channel]:
			del Global.account_cache[channel][nick]
			Logger.log("w", "Removing %s from %s" % (nick, channel))
	if account != None and account != False:
		Expire.bump_last(account)
hooks["KICK"] = kick

def quit(instance, source, _):
	curtime = time.time()
	nick = Irc.get_nickname(source, "")
	account = None
	with Global.account_lock:
		if nick == instance:
			chans = []
			for channel in Global.account_cache:
				if nick in Global.account_cache[channel]:
					chans.append(channel)
			for channel in chans:
					del Global.account_cache[channel]
					Logger.log("w", "Removing cache for " + channel)
			return
		for channel in Global.account_cache:
			if nick in Global.account_cache[channel] and channel[0] != "@":
				account = Global.account_cache[channel][nick]
				if account != None:
					break
		for channel in Global.account_cache:
			if nick in Global.account_cache[channel] and channel[0] != "@":
				del Global.account_cache[channel][nick]
				Logger.log("w", "Removing %s from %s" % (nick, channel))
	if account != None and account != False:
		Expire.bump_last(account)
hooks["QUIT"] = quit

def account(instance, source, account):
	curtime = time.time()
	if account == "*":
		account = False
	nick = Irc.get_nickname(source, "")
	with Global.account_lock:
		for channel in Global.account_cache:
			if nick in Global.account_cache[channel] and channel[0] != "@":
				if channel in Config.config["welcome_channels"] and not account and not Transactions.check_exists(nick) and (nick not in Global.welcome_list or Global.welcome_list[nick] + (60*10) < curtime):
					Global.welcome_list[nick] = curtime
					Irc.instance_send(instance, ("PRIVMSG", channel, "Welcome our newest Rogeteer - %s! Try &help, &rogerme and &faucet to get started!" % (nick)), priority = 20, lock = False)
				elif channel in Config.config["welcome_channels"] and account and Transactions.check_exists(nick) and (nick not in Global.welcome_list or Global.welcome_list[nick] + (60*10) < curtime):
					Global.welcome_list[nick] = curtime
					welcome_str = str(Commands.random_line('quotes_welcome'))
					Irc.instance_send(instance, ("NOTICE", nick, "Welcome back %s! %s" % (nick, welcome_str)), priority = 20, lock = False)
				Global.account_cache[channel][nick] = account
				Logger.log("w", "Propagating %s=%s into %s" % (nick, account, channel))
		Global.nick_source_cache[nick] = source
		if account != False and account != None:
			Global.acctnick_list[account] = nick
	if account != None and account != False:
		Expire.bump_last(account)
hooks["ACCOUNT"] = account

def _nick(instance, source, newnick):
	nick = Irc.get_nickname(source, "")
	account = None
	with Global.account_lock:
		for channel in Global.account_cache:
			if nick in Global.account_cache[channel]:
				account = Global.account_cache[channel][nick]
				Global.nick_source_cache[nick] = source
				if account != False and account != None and channel[0] != "@":
					Global.acctnick_list[account] = newnick
				if account != None:
					break
		for channel in Global.account_cache:
			if nick in Global.account_cache[channel] and channel[0] != "@":
				Global.account_cache[channel][newnick] = Global.account_cache[channel][nick]
				Logger.log("w", "%s -> %s in %s" % (nick, newnick, channel))
				del Global.account_cache[channel][nick]
	if account != None and account != False:
		Expire.bump_last(account)
hooks["NICK"] = _nick

def names(instance, _, __, eq, channel, names):
	names = names.split(" ")
	with Global.account_lock:
		for n in names:
			n = Irc.strip_nickname(n)
			Global.account_cache[channel][n] = None
hooks["353"] = names

def error(instance, *_):
	Logger.log("ce", instance + " disconnected")
	raise socket.error()
hooks["ERROR"] = error

def whois_host(instance, _, __, target, *___):
	Global.instances[instance].lastwhois = False
hooks["311"] = whois_host

def whois_ident(instance, _, __, target, account, ___):
	Global.instances[instance].lastwhois = account
hooks["330"] = whois_ident

def whois_end(instance, _, __, target, ___):
	try:
		nick, q = Global.instances[instance].whois_queue.get(False)
		if Irc.equal_nicks(target, nick):
			Logger.log("w", instance + ": WHOIS of " + target + " is " + repr(Global.instances[instance].lastwhois))
			q.put(Global.instances[instance].lastwhois, True)
		else:
			Logger.log("we", instance + ": WHOIS reply for " + target + " but queued " + nick + " returning None")
			q.put(None, True)
		Global.instances[instance].lastwhois = None
		Global.instances[instance].whois_queue.task_done()
	except Queue.Empty:
		Logger.log("we", instance + ": WHOIS reply for " + target + " but nothing queued")
hooks["318"] = whois_end

def cap(instance, _, __, ___, caps):
	if caps.rstrip(" ") == "sasl":
		Irc.instance_send(instance, ("AUTHENTICATE", "PLAIN"), lock = False)
hooks["CAP"] = cap

def authenticate(instance, _, data):
	if data == "+":
		load = Config.config["account"] + "\0" + Config.config["account"] + "\0" + Config.config["password"]
		Irc.instance_send(instance, ("AUTHENTICATE", load.encode("base64").rstrip("\n")), lock = False)
hooks["AUTHENTICATE"] = authenticate

def sasl_success(instance, _, data, __):
	Logger.log("c", "Finished authentication")
	Irc.instance_send(instance, ("CAP", "END"), lock = False)
	Irc.instance_send(instance, ("CAP", "REQ", "extended-join account-notify"), lock = False)
hooks["903"] = sasl_success
