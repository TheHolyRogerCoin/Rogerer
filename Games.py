# coding=utf8
import sys, os, subprocess, time, datetime, math, pprint, traceback, operator, random
import Irc, Transactions, Blocknotify, Logger, Global, Hooks, Config
from Commands import parse_amount, print_amount, validate_user, coloured_text, is_soak_ignored, soak, random_seed_gen, pot_balance
from collections import OrderedDict

games = {}

def check_gamble_timer(instance, targetchannel, cmd_args, nick, source, acct, timers = { "timer_min": 5, "timer_max": 15, "penalty_min": 10, "penalty_max": 20 }, to_admin = False, allowed_anywhere = False):
	curtime = time.time()
	timer_min = timers["timer_min"]
	timer_max = timers["timer_max"]
	penalty_min = timers["penalty_min"]
	penalty_max = timers["penalty_max"]
	if (targetchannel not in Global.gamble_list) or (acct not in Global.gamble_list[targetchannel]):
		return False
	if targetchannel not in Config.config["botchannels"] and not allowed_anywhere:
		timer_min = 60*timer_min
		timer_max = 60*timer_max
		penalty_min = 90*penalty_min
		penalty_max = 90*penalty_max
		str_botchannel = "Please use game commands in #RogerCasino. "
		is_admin = False
	else:
		str_botchannel = ""
		is_admin = Irc.is_admin(source)
	timer = random.randint((timer_min),(timer_max))
	lastGambleTime = int(Global.gamble_list[targetchannel][acct])
	Logger.log("c","%s lastGambleTime at %i" % (nick, lastGambleTime))

	if not to_admin:
		game_ident = ['@POKER%', '@BLACKJACK%', '@ROUL%', '@LOTTO%']
		interval = "24 hours"
		spent_24h = Transactions.get_game_stats(instance, mode = "in-sum", game_ident = game_ident, acct = acct, interval = interval, count = False)
		won_24h = Transactions.get_game_stats(instance, mode = "out-sum", game_ident = game_ident, acct = acct, interval = interval, count = False)
		net_won_24h = (int(won_24h) - int(spent_24h))
		Logger.log("c","Game stats @ %s: Nick: %s Total Spent: %i, Total Won: %i, Net Won: %i" % (interval, nick, spent_24h, won_24h, net_won_24h))
		interval = "7 days"
		spent_7d = Transactions.get_game_stats(instance, mode = "in-sum", game_ident = game_ident, acct = acct, interval = interval, count = False)
		won_7d = Transactions.get_game_stats(instance, mode = "out-sum", game_ident = game_ident, acct = acct, interval = interval, count = False)
		net_won_7d = (int(won_7d) - int(spent_7d))
		Logger.log("c","Game stats @ %s: Nick: %s Total Spent: %i, Total Won: %i, Net Won: %i" % (interval, nick, spent_7d, won_7d, net_won_7d))
		soft_winning_cap = parse_amount(Config.config["gamble_params"]["soft_winning_cap"])
		hard_winning_cap = parse_amount(Config.config["gamble_params"]["hard_winning_cap"])
		multiplier_winning_cap = parse_amount(Config.config["gamble_params"]["multiplier_winning_cap"])
		if (net_won_24h > soft_winning_cap):
			if (net_won_24h > hard_winning_cap):
				new_timer = timer+(60*60*3)
			else:
				new_timer = timer+(60*60*1)
			if lastGambleTime < curtime + new_timer:
				timer = new_timer
				Logger.log("c","Game stats @ %s: Nick: %s Total Spent: %i, Total Won: %i, Net Won: %i" % (interval, nick, spent_24h, won_24h, net_won_24h))
	if (not Config.config["gamble_params"]["force_timer"]) and (is_admin or acct not in Global.gamble_list[targetchannel] or Irc.is_super_admin(source)):
		return False
	if len(cmd_args) > 0 and nick in Global.response_read_timers:
		timer = 0
	if lastGambleTime + timer > curtime:
		if lastGambleTime + timer > curtime + (timer_min/3) and lastGambleTime + timer < curtime + (40*24*60*60):
			penalty = random.randint((penalty_min),(penalty_max))
			if not to_admin and (net_won_7d > hard_winning_cap):
					penalty = penalty*4
					if (net_won_7d > multiplier_winning_cap):
						penalty = penalty*(int(net_won_7d/multiplier_winning_cap))
			Global.gamble_list[targetchannel][acct] = lastGambleTime + penalty
			Logger.log("c","%s received penalty of %i %s, gambletime: %i, curtime: %i, timer %i %s" % (nick, ((penalty)/(60*60) if penalty > (60*60) else (penalty)/(60) ), ("hours" if penalty > (60*60) else "minutes" ), lastGambleTime, curtime, ((timer)/(60*60) if timer > (60*60) else (timer)/(60) ), ("hours" if timer > (60*60) else "minutes" )))
			lastGambleTime = int(Global.gamble_list[targetchannel][acct])
		timerApprx = random.randint(timer,timer+(30))
		difference = (lastGambleTime + timerApprx - curtime)
		if difference > ((60*60)*24):
			difference = difference/((60*60)*24)
			timeUnit = "days"
		elif difference > 60*60:
			difference = difference/(60*60)
			timeUnit = "hours"
		elif difference > 60:
			difference = difference/60
			timeUnit = "minutes"
		else:
			timeUnit = "seconds"
		if not to_admin and net_won_24h > soft_winning_cap:
			r_str = "You've won a lot today! "
		elif not to_admin:
			r_str = "Roger safely - begambleaware.org. "
		else:
			str_botchannel = ""
			r_str = ""
		Logger.log("c","%s timer vals: %s, timer: %i, lastGambleTime: %i" % (nick, timers, timer, lastGambleTime))
		return "%s%sWait %.1f %s." % (str_botchannel, r_str, difference, timeUnit)
	else:
		return False

def add_gamble_timer(targetchannel, acct, curtime):
	if targetchannel not in Global.gamble_list:
		Global.gamble_list[targetchannel] = {}
	Global.gamble_list[targetchannel][acct] = curtime

def add_read_timer(nick, time, cmd = "bj", vals = {}):
	Global.response_read_timers[nick] = {}
	Global.response_read_timers[nick]["vals"] = vals
	Global.response_read_timers[nick]["time"] = time
	Global.response_read_timers[nick]["cmd"] = cmd


def check_gamble_raise(nick = False):
	t = time.time()
	if nick and "@gamblelimitraise" in Global.gamble_list and nick in Global.gamble_list["@gamblelimitraise"] and "limit" in Global.gamble_list["@gamblelimitraise"][nick]:
		if "time" in Global.gamble_list["@gamblelimitraise"][nick] and Global.gamble_list["@gamblelimitraise"][nick]["time"] > t - (60*60):
			try:
				maxbet = Global.gamble_list["@gamblelimitraise"][nick]["limit"]
				Global.gamble_list["@gamblelimitraise"].pop(nick)
				return maxbet
			except ValueError as e:
				Global.gamble_list["@gamblelimitraise"].pop(nick)
				return False
		else:
			Global.gamble_list["@gamblelimitraise"].pop(nick)
			return False
	return False

def roger_that(req, arg):
	"""%roger-that games must be started by mods."""
	if len(arg) < 1 or not (arg[0] == "start" or arg[0] == "debug" or arg[0] == "auto" or arg[0] == "end-game" or (len(arg[0]) >= 5 and arg[0][0:5].lower() == "roger")):
		return
	toacct = Irc.account_names([req.nick])[0]
	acct = req.instance
	host = Irc.get_host(req.source)
	curtime = time.time()
	amount = parse_amount(69)
	random.seed(random_seed_gen())
	if "@HOSTS" not in Global.gamble_list: Global.gamble_list["@HOSTS"] = {}
	user_valid, toacct = validate_user(toacct, host = host, nick = req.nick, altnick = req.altnick, allow_discord_nicks = True, hostlist = Global.gamble_list["@HOSTS"])
	if user_valid != True:
		if "Quiet" == user_valid: return
		return req.notice_private(user_valid)
	if Config.config['maintenance_mode'] and not Irc.is_super_admin(req.source): return req.notice_private("Bot under maintenance.")
	if (req.target == req.nick or req.target not in Config.config["instances"][req.instance]) and not Irc.is_super_admin(req.source):
		return req.reply("Can't roger that in private!")
	if is_soak_ignored(toacct):
		return req.notice_private("You cannot participate in ROGER THAT")

	if Irc.is_admin(req.source) and arg[0] == "start" or arg[0] == "debug":
		if len(arg) > 1:
			try:
				amount = parse_amount(arg[1])
				if amount > parse_amount(69): amount = parse_amount(69)
			except ValueError as e:
				return req.notice_private(str(e))
		if "@roger_that" not in Global.gamble_list or Irc.is_super_admin(req.source):
			for welcome_channel in Config.config["welcome_channels"]:
				timer_vals = { "timer_min": 4, "timer_max": 8, "penalty_min": 5, "penalty_max": 15 }
				rt_timer = check_gamble_timer(instance = req.instance, targetchannel = welcome_channel, cmd_args = [], nick = False, source = req.source, acct = acct, timers = timer_vals, to_admin = True)
				if rt_timer: return req.reply(rt_timer)
				Global.gamble_list["@roger_that"] = amount
				add_gamble_timer(welcome_channel, acct, curtime)
				if arg[0] == "debug":
					req.reply(coloured_text(text = "ROGER?!???!", rainbow = True, channel = welcome_channel))
				else:
					Irc.instance_send(req.instance, ("PRIVMSG", welcome_channel, coloured_text(text = "ROGER?!???!", rainbow = True, channel = welcome_channel)))
				add_read_timer("@roger_that", curtime, cmd = "roger-that")
		else:
			req.reply("Game in progress. Use 'end-game'.")
		return
	elif "@roger_that" not in Global.gamble_list:
		return req.reply(gethelp("roger-that"))
	elif "@roger_that_prevwin" in Global.gamble_list and Global.gamble_list["@roger_that_prevwin"] == toacct:
		if arg[0] == "end-game": return
		return req.notice_private("Don't be greedy! Let someone else have a go!")

	token = Logger.token()
	try:
		amount = Global.gamble_list["@roger_that"]
		Global.gamble_list["@roger_that_prevwin"] = toacct
		Global.gamble_list.pop("@roger_that")
		if "@roger_that" in Global.response_read_timers: Global.response_read_timers.pop("@roger_that")
		Global.gamble_list["@HOSTS"][host] = toacct
		Transactions.tip(token, acct, toacct, amount, tip_source = "@ROGER_THAT")
		won_string = "%s %s %s" % (coloured_text(text = "WON", colour = "03", channel = req.target), print_amount(amount), coloured_text(text = Config.config["coinab"], colour = "03", channel = req.target))
		if arg[0] == "end-game":
			reply_str = "No one ROGER'd in time so %s claimed it! %s" % (req.altnick, won_string)
		else:
			reply_str = "%s ROGER'd first! %s!" % (req.altnick, won_string)
		req.say("%s%s" % (reply_str, pot_balance(req.instance)))
	except Transactions.NotEnoughMoney:
		return req.notice_private("We're all out of %s!!" % (Config.config["coinab"]))

def lotto(req, arg):
	"""%lotto <donation> <luckynumber> - Donate 'donation' (min 30) to pot for chance of winning a goldenshower (3000) if 'luckynumber' (0-100) picked (default 69)."""
	if len(arg) < 1:
		return req.reply(gethelp("lotto"))
	acct = Irc.account_names([req.nick])[0]
	host = Irc.get_host(req.source)
	minbet = parse_amount(Config.config["gamble_params"]["@lotto"]["minbet"], min_amount='.0005')
	chances = 1
	curtime = time.time()
	random.seed(random_seed_gen())
	if "@Gamble_buildup" not in Global.gamble_list:
		Global.gamble_list["@Gamble_buildup"] = 0
	if "@HOSTS" not in Global.gamble_list: Global.gamble_list["@HOSTS"] = {}
	user_valid = validate_user(acct, host = host, nick = req.nick, hostlist = Global.gamble_list["@HOSTS"])
	if user_valid != True: return req.notice_private(user_valid)
	if Config.config['maintenance_mode'] and not Irc.is_super_admin(req.source): return req.notice_private("Bot under maintenance.")
	if (req.target == req.nick or req.target not in Config.config["instances"][req.instance]) and not Irc.is_super_admin(req.source):
		return req.reply("Can't lotto in private!")
	timer_vals = Config.config["gamble_params"]["@lotto"]["timers"]
	gamble_timer_reply = check_gamble_timer(instance = req.instance, targetchannel = req.target, cmd_args = arg, nick = req.nick, source = req.source, acct = acct, timers = timer_vals, allowed_anywhere = True)
	if gamble_timer_reply: return req.reply(gamble_timer_reply)
	toacct = req.instance
	try:
		amount = parse_amount(arg[0], acct, min_amount='.0005')
	except ValueError as e:
		return req.notice_private(str(e))
	if len(arg) < 2:
		luckynumber = 69
	else:
		luckynumber = int(arg[1])
	if amount < minbet:
		return req.reply("Don't be so cheap! %s %s minimum!" % (print_amount(minbet), Config.config["coinab"]), True)
	elif amount > (minbet * 5):
		chances = int(chances + (amount/parse_amount('100')))
	if "@Gamble_buildup" in Global.gamble_list:
		if Global.gamble_list["@Gamble_buildup"] > parse_amount('3000'):
			multiplier = 2
		else:
			multiplier = 1
		Global.gamble_list["@Gamble_buildup"] = Global.gamble_list["@Gamble_buildup"] + amount
		chances = int(chances + (Global.gamble_list["@Gamble_buildup"]/(parse_amount('200')/multiplier)))
	lotto=[]
	for i in range (chances):
		lotto.append(random.randint(1,100))
	token = Logger.token()
	Logger.log("c","Lotto triggered, Chances: %i" % (chances))
	try:
		Transactions.tip(token, acct, toacct, amount, tip_source = "@LOTTO_START")
		add_gamble_timer(targetchannel = req.target, acct = acct, curtime = curtime)
		Global.gamble_list["@HOSTS"][host] = acct
		if luckynumber in lotto: # or (Irc.is_admin(req.source) and luckynumber == random.randint(68,70)):
			if Transactions.balance(toacct) < parse_amount("goldenshower",toacct):
				return req.reply("We're all out of %s!!" % (Config.config["coinab"]), True)
			Global.gamble_list["@Gamble_buildup"] = 0
			won_string = "%s %s %s" % (coloured_text(text = "WON a golden shower", colour = "03", channel = req.target), print_amount(amount), coloured_text(text = Config.config["coinab"], colour = "03", channel = req.target))
			req.say("%s played %s %s (%i%% chance) and %s! Be moist and rejoice! %s%s" % (req.nick, print_amount(amount), Config.config["coinab"], chances, coloured_text(text = "WON a golden shower", colour = "03", channel = req.target), coloured_text(text = "Splashback!", colour = "03", channel = req.target), pot_balance(req.instance)))
			try:
				Transactions.tip(token, toacct, acct, parse_amount("goldenshower",toacct), tip_source = "@LOTTO_WIN") # accts swapped
			except Transactions.NotEnoughMoney:
				return req.notice_private("%s Bot ran out of winnings!" % (reply))
			soak(req, ["splashback", "1440"], from_instance = True)
		else:
			req.say("%s played %s %s but %s [%s]" % (req.nick, print_amount(amount), Config.config["coinab"], coloured_text(text = "left everyone dry :(", colour = "04", channel = req.target), token))
		return
	except Transactions.NotEnoughMoney:
		req.notice_private("You tried to play %s %s but you only have %s %s" % (print_amount(amount), Config.config["coinab"], print_amount(Transactions.balance(acct)), Config.config["coinab"]))
		return

def cards_decks(amt_decks = 1, split_deck = False):
	random.seed(random_seed_gen())
	ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
	suits = ['♠','♦','♥','♣']
	deck = [rank+suit for suit in suits for rank in ranks]
	multi_deck = []
	for deckno in range(amt_decks):
		onedeck = deck
		for shuffle in range(random.randint(5, 20)):
			random.shuffle(onedeck)
		multi_deck += onedeck
	for shuffle in range(random.randint(5, 20)):
		random.shuffle(multi_deck)
	if split_deck:
		deck = multi_deck[-len(multi_deck)/2:]
	else:
		deck = multi_deck
	return deck

def cards_hit(hand, deck):
	card = deck.pop(0)
	hand.append(card)
	return hand,deck

def bj_deal():
	deck = cards_decks(amt_decks = Config.config["gamble_params"]["@blackjack"]["decks"], split_deck = True)
	phand = []
	dhand = []
	phand.append(deck.pop(0))
	dhand.append(deck.pop(0))
	phand.append(deck.pop(0))
	dhand.append(deck.pop(0))
	return dhand,phand,deck

def bj_total(hand, show_softhand = False):
	total = 0
	aceflag=False
	softhand=False
	for c in hand:
		card = c[:-3]
		if card == "J" or card == "Q" or card == "K":
			total+= 10
		elif card == "A":
			aceflag=True
			total+= 1
		else:
			total+= parse_amount(card, force_no_decimal_calc = True)
	if aceflag and total<12:
		total+= 10
		softhand = True
	if show_softhand:
		return total, softhand
	return total



def bj_result_string(dealer_hand, player_hand, player_total = False, hand_softhand = False, dealer_total = False, channel = False):
	ptotal = ""
	dtotal = ""
	if hand_softhand:
		p_soft = "~"
	else:
		p_soft = ""
	if player_total:
		ptotal = " %s(%i)" % (p_soft, player_total)
	if dealer_total:
		dtotal = " (%i)" % (dealer_total)
		dealer_hand_mask = dealer_hand
	else:
		dealer_hand_mask = []
		for i in range(len(dealer_hand)):
			if i == 0: dealer_hand_mask.append(dealer_hand[i])
			else: dealer_hand_mask.append('??')
	dhand_str = '['
	for card in dealer_hand_mask:
		if card[-3:] == '♥' or card[-3:] == '♦':
			dhand_str = "%s %s%s" % (dhand_str, card[:-3], coloured_text(text = card[-3:], colour = "04", channel = channel))
		else:
			dhand_str = "%s %s" % (dhand_str, card)
	dhand_str = "%s ]" % (dhand_str)
	dealer_hand_mask = dhand_str
	# dealer_hand_mask = '[ '+' '.join(card for card in dealer_hand_mask)+' ]'
	phand_str = '['
	for card in player_hand:
		if card[-3:] == '♥' or card[-3:] == '♦':
			phand_str = "%s %s%s" % (phand_str, card[:-3], coloured_text(text = card[-3:], colour = "04", channel = channel))
		else:
			phand_str = "%s %s" % (phand_str, card)
	phand_str = "%s ]" % (phand_str)
	hand_mask = phand_str
	# hand_mask = '[ '+' '.join(card for card in player_hand)+' ]'
	return hand_mask+ptotal+"  <->  House: "+dealer_hand_mask+dtotal

def bj_score(req, dealer_hand, player_hand, deal = False, stand = False, split = False, hand1 = False, force_dealerReveal = False):
	msg = False
	hand_win = False
	hand_draw = False
	hand_playon = False
	hand_payout_bj = False
	as_notice = False
	player_total, hand_softhand = bj_total(player_hand, show_softhand = True)
	dealer_total = bj_total(dealer_hand)
	dealerReveal = True
	if len(player_hand) == 2: deal = True
	if not player_total >= 21 and not dealer_total >= 21 and not stand:
		msg = "\x02[H]\x02it or \x02[S]\x02tand"
		if deal == True and not split:
			if bj_total([player_hand[0]]) == bj_total([player_hand[1]]):
				msg = "\x02[H]\x02it , \x02[S]\x02tand , \x02[D]\x02ouble-down or S\x02[P]\x02lit"
			else:
				msg = "\x02[H]\x02it , \x02[S]\x02tand or \x02[D]\x02ouble-down"
		hand_playon = True
		dealerReveal = False
		as_notice = True
	elif player_total == 21 and deal == True and len(player_hand) == 2:
		msg = "Dealer gave you a %s!!" % (coloured_text(text = "BJ", colour = "03", channel = req.target))
		hand_payout_bj = True
		hand_win = True
	elif dealer_total == 21 and deal == True and len(dealer_hand) == 2:
		msg =  "%s You gave the dealer a %s." % (coloured_text(text = ":<", colour = "04", channel = req.target), coloured_text(text = "BJ", colour = "04", channel = req.target))
	elif player_total > 21:
		msg = "%s You %s your load." % (coloured_text(text = ":<", colour = "04", channel = req.target), coloured_text(text = "busted", colour = "04", channel = req.target))
	elif dealer_total > 21:	   
		msg = "Dealer %s his load!" % (coloured_text(text = "busts", colour = "03", channel = req.target))
		hand_win = True
	elif player_total < dealer_total:
		msg ="%s Dealer %s" % (coloured_text(text = ":<", colour = "04", channel = req.target), coloured_text(text = "came closer.", colour = "04", channel = req.target))
	elif player_total > dealer_total:   
		msg = "You %s" % (coloured_text(text = "came closer!", colour = "03", channel = req.target))
		hand_win = True
	elif player_total == dealer_total:   
		msg = "%s Draw" % (coloured_text(text = ":S", colour = "02", channel = req.target))
		hand_draw = True
	if (dealerReveal and (not split or not hand1)) or (force_dealerReveal):
		results = bj_result_string(dealer_hand = dealer_hand, player_hand = player_hand, player_total = player_total, dealer_total = dealer_total, channel = req.target)
	else:
		results = bj_result_string(dealer_hand = dealer_hand, player_hand = player_hand, player_total = player_total, hand_softhand = hand_softhand, channel = req.target)
	if msg and split:
		if hand1:
			if not hand_playon and not force_dealerReveal:
				msg = "Switching to HAND2  ..."
			msg = "  (HAND1)  ...  %s" % (msg)
		else:
			msg = "  (HAND2)  ...  %s" % (msg)
	elif msg:
		msg = "  ...  %s" % (msg)
	else:
		msg = ""
	reply = results+msg
	return hand_win, reply, hand_playon, hand_draw, hand_payout_bj, as_notice

def bj_player_hit(player_hand, dealer_hand, deck, req, split, hand1 = False):
	player_hand, deck = cards_hit(player_hand, deck)
	while (not split or not hand1) and bj_total(player_hand) >= 21 and bj_total(dealer_hand) < 17:
		dealer_hand, deck = cards_hit(dealer_hand, deck)
	hand_win, hand_reply, hand_playon, hand_draw, hand_payout_bj, as_notice = bj_score(req, dealer_hand, player_hand, split = split, hand1 = hand1)
	return hand_win, hand_reply, hand_playon, hand_draw, hand_payout_bj, player_hand, dealer_hand, deck, as_notice

def bj_player_stand(player_hand, dealer_hand, deck, req, split, hand1 = False, game_num = 1, force_dealerReveal = False):
	while (not split or not (hand1 and game_num == 1)) and bj_total(dealer_hand) < 17:
		dealer_hand, deck = cards_hit(dealer_hand, deck)
	hand_win, hand_reply, hand_playon, hand_draw, hand_payout_bj, as_notice = bj_score(req, dealer_hand, player_hand, split = split, stand = True, hand1 = hand1, force_dealerReveal = force_dealerReveal)
	return hand_win, hand_reply, hand_playon, hand_draw, hand_payout_bj, player_hand, dealer_hand, deck

def bj_player_auto(player_hand, dealer_hand, deck, req, split, hand1 = False):
	while bj_total(player_hand) < 17:
		player_hand, deck = cards_hit(player_hand, deck)
	while (not split or not hand1) and bj_total(dealer_hand) < 17:
		dealer_hand, deck = cards_hit(dealer_hand, deck)
	hand_win, hand_reply, hand_playon, hand_draw, hand_payout_bj, as_notice = bj_score(req, dealer_hand, player_hand, split = split, stand = True, hand1 = hand1)
	return hand_win, hand_reply, hand_playon, hand_draw, hand_payout_bj, player_hand, dealer_hand, deck

def hand_winner_tip(req, bet, pot_acct, winner_acct, token, hand_reply, hand_payout_bj = False):
	if hand_payout_bj:
		multiplier = 1.5
		odds = "[3to2]"
	else:
		multiplier = 1.0
		odds = "[1to1]"
	winmsg = game_winner_tip(token, bot_acct = pot_acct, player_acct = winner_acct, total_bet = bet, game = "@BLACKJACK_WIN", multiplier = multiplier)
	if not winmsg: return
	won_string = "%s %s" % (coloured_text(text = "WON", colour = "03", channel = req.target), winmsg)
	return req.reply("%s %s %s!%s" % (hand_reply, won_string, odds, pot_balance(req.instance)))

def bj_cancel(token, bot_acct, player_acct, bet, bet2):
	msg = "Previous game cancelled, bet(s) partially refunded."
	if bet > 0:
		try:
			Transactions.tip(token, source = bot_acct, target = player_acct, amount = (bet/2), tip_source = "@BLACKJACK") #toacct swapped
		except Transactions.NotEnoughMoney:
			return req.notice_private("Bot ran out of money to return bet!")
	if bet2 > 0:
		try:
			Transactions.tip(token, source = bot_acct, target = player_acct, amount = (bet2/2), tip_source = "@BLACKJACK") #toacct swapped
		except Transactions.NotEnoughMoney:
			return req.notice_private("Bot ran out of money to return bet!")
	return msg

def bj(req, arg):
	"""%bj <bet> - Play Blackjack with 'bet' for chance to win 2x"""
	if len(arg) < 1:
		return req.reply(gethelp("bj"))
	if len(arg) > 1:
		conf_switch = arg[1]
	else:
		conf_switch = False
	acct = Irc.account_names([req.nick])[0]
	host = Irc.get_host(req.source)
	minbet = parse_amount(Config.config["gamble_params"]["@blackjack"]["minbet"], min_amount='.0005')
	maxbet = parse_amount(Config.config["gamble_params"]["@blackjack"]["maxbet"], min_amount='.0005')
	# if Irc.is_admin(req.source):
	# 	maxbet = 10000
	tempmaxbet = check_gamble_raise(req.nick)
	if tempmaxbet: maxbet = tempmaxbet
	# if not Irc.is_admin(req.source):
	# 	return # temporary disable
	if "@HOSTS" not in Global.gamble_list: Global.gamble_list["@HOSTS"] = {}
	user_valid = validate_user(acct, host = host, nick = req.nick, hostlist = Global.gamble_list["@HOSTS"])
	if user_valid != True: return req.notice_private(user_valid)
	if Config.config['maintenance_mode'] and not Irc.is_super_admin(req.source): return req.notice_private("Bot under maintenance.")
	if (req.target == req.nick or req.target not in Config.config["instances"][req.instance]) and not Irc.is_super_admin(req.source):
		return req.reply("Can't bj in private!")
	if req.nick in Global.response_read_timers and not Global.response_read_timers[req.nick]["cmd"] == "bj":
		return req.notice_private("One game at a time!")
	curtime = time.time()
	random.seed(random_seed_gen())
	timer_vals = Config.config["gamble_params"]["@blackjack"]["timers"]
	gamble_timer_reply = check_gamble_timer(instance = req.instance, targetchannel = req.target, cmd_args = arg, nick = req.nick, source = req.source, acct = acct, timers = timer_vals)
	if gamble_timer_reply: return req.reply(gamble_timer_reply)
	toacct = req.instance
	choice = arg[0].lower()
	choice_digits_accepted = [1,2,3,4]
	if arg[0].isdigit():
		choice_is_digit = int(arg[0])
	else:
		choice_is_digit = False
	token = Logger.token()
	Logger.log("c","BJ triggered: %s Choice: %s" % (arg, choice))
	if len(arg) > 0 and not (choice_is_digit != False and choice_is_digit not in choice_digits_accepted) and req.nick in Global.response_read_timers:
		if choice == "end-game":
			Global.response_read_timers.pop(req.nick)
			Logger.log("c","BJ ended, timer removed")
			return req.notice_private("Don't fall asleep during a BJ! Bet not refunded!")
		bj_start = Global.response_read_timers[req.nick]["vals"]["bj_start"]
		bj_public = Global.response_read_timers[req.nick]["vals"]["bj_public"]
		deck = Global.response_read_timers[req.nick]["vals"]["deck"]
		dealer_hand = Global.response_read_timers[req.nick]["vals"]["dealer_hand"]
		player_hand = Global.response_read_timers[req.nick]["vals"]["player_hand"]
		bet = Global.response_read_timers[req.nick]["vals"]["bet"]
		player_hand2 = Global.response_read_timers[req.nick]["vals"]["player_hand2"]
		bet2 = Global.response_read_timers[req.nick]["vals"]["bet2"]
		game_num = Global.response_read_timers[req.nick]["vals"]["game_num"]
		hand_win = Global.response_read_timers[req.nick]["vals"]["hand_win"]
		hand_draw = Global.response_read_timers[req.nick]["vals"]["hand_draw"]
		Logger.log("c","BJ stored vals: BJ_Start: %s, BJ_Public: %s, Game_Num: %i, Bet1: %i, Bet2: %i, Hand1_Win: %s, Hand1_Draw: %s, Deck Count: %i, Dealer Hand Count: %i, Player Hand1 Count: %i, Player Hand2 Count: %i" % (bj_start, bj_public, game_num, bet, bet2, hand_win, hand_draw, len(deck), len(dealer_hand), len(player_hand), len(player_hand2)))
		hand2_reply = hand_reply = ""
		choiceFound = hand_playon = hand2_playon = hand_payout_bj = hand2_payout_bj = hand2_win = hand2_draw = as_notice = False
		if bet2 > 0:
			bj_split = True
		else:
			bj_split = False
		if bj_split and game_num == 2:
			if choice == "hit" or choice == "h" or choice == "h2" or choice == "1":
				choiceFound = True
				hand2_win, hand2_reply, hand2_playon, hand2_draw, hand2_payout_bj, player_hand2, dealer_hand, deck, as_notice = bj_player_hit(player_hand = player_hand2, dealer_hand = dealer_hand, deck = deck, req = req, split = bj_split)
			elif choice == "stand" or choice == "s" or choice == "s2" or choice == "2":
				choiceFound = True
				hand2_win, hand2_reply, hand2_playon, hand2_draw, hand2_payout_bj, player_hand2, dealer_hand, deck = bj_player_stand(player_hand = player_hand2, dealer_hand = dealer_hand, deck = deck, req = req, split = bj_split)
			elif (len(arg) == 1 and choice == "auto") or choice == "auto" or choice == "auto2":
				choiceFound = True
				hand2_win, hand2_reply, hand2_playon, hand2_draw, hand2_payout_bj, player_hand2, dealer_hand, deck = bj_player_auto(player_hand = player_hand2, dealer_hand = dealer_hand, deck = deck, req = req, split = bj_split)
			else:
				choice = "none"
		elif choice == "hit" or choice == "h" or choice == "h1" or choice == "1":
			choiceFound = True
			hand_win, hand_reply, hand_playon, hand_draw, hand_payout_bj, player_hand, dealer_hand, deck, as_notice = bj_player_hit(player_hand = player_hand, dealer_hand = dealer_hand, deck = deck, req = req, split = bj_split, hand1 = True)
		elif choice == "stand" or choice == "s" or choice == "s1" or choice == "2":
			choiceFound = True
			hand_win, hand_reply, hand_playon, hand_draw, hand_payout_bj, player_hand, dealer_hand, deck = bj_player_stand(player_hand = player_hand, dealer_hand = dealer_hand, deck = deck, req = req, split = bj_split, hand1 = True)
		elif choice == "auto" or choice == "auto1":
			choiceFound = True
			hand_win, hand_reply, hand_playon, hand_draw, hand_payout_bj, player_hand, dealer_hand, deck = bj_player_auto(player_hand = player_hand, dealer_hand = dealer_hand, deck = deck, req = req, split = bj_split, hand1 = True)
		elif bj_start and (choice == "d" or choice == "dd" or choice == "doubledown" or choice == "3"):
			choiceFound = True
			try:
				Transactions.tip(token, acct, toacct, bet, tip_source = "@BLACKJACK")
				bet = bet + bet
				hand_win, hand_reply, hand_playon, hand_draw, hand_payout_bj, player_hand, dealer_hand, deck, as_notice = bj_player_hit(player_hand = player_hand, dealer_hand = dealer_hand, deck = deck, req = req, split = bj_split, hand1 = True)
				hand_win, hand_reply, hand_playon, hand_draw, hand_payout_bj, player_hand, dealer_hand, deck = bj_player_stand(player_hand = player_hand, dealer_hand = dealer_hand, deck = deck, req = req, split = bj_split, hand1 = True)
				if not hand_playon:
					as_notice = False
			except Transactions.NotEnoughMoney:
				return req.notice_private("You tried to double down %s %s but you only have %s %s" % (print_amount(bet), Config.config["coinab"], print_amount(Transactions.balance(acct)), Config.config["coinab"]))
		elif bj_start and (choice == "split" or choice == "p" or choice == "4") and (bj_total([player_hand[0]]) == bj_total([player_hand[1]])) or (Irc.is_super_admin(req.source) and len(arg) == 2 and arg[1] == "givemeasplit"):
			choiceFound = True
			try:
				Transactions.tip(token, acct, toacct, bet, tip_source = "@BLACKJACK")
				bet2 = bet
				bj_split = True
				player_hand2 = [player_hand.pop(1)]
				player_hand, deck = cards_hit(player_hand, deck)
				player_hand2, deck = cards_hit(player_hand2, deck)
				hand_win, hand_reply, hand_playon, hand_draw, hand_payout_bj, as_notice = bj_score(req, dealer_hand, player_hand, split = bj_split, hand1 = True)
			except Transactions.NotEnoughMoney:
				return req.notice_private("You tried to split on %s %s but you only have %s %s" % (print_amount(bet), Config.config["coinab"], print_amount(Transactions.balance(acct)), Config.config["coinab"]))
		else:
			choice = "none"
		if choiceFound:
			Global.response_read_timers.pop(req.nick)
			Logger.log("c","BJ choice found, read response cleared")
			if bj_split and game_num == 1 and not hand_playon:
				Logger.log("c","BJ switching to HAND2")
				game_num = 2
				hand2_playon = True
				hand2_win, hand2_reply, hand2_playon, hand2_draw, hand2_payout_bj, as_notice = bj_score(req, dealer_hand, player_hand2, split = bj_split)
			if game_num == 2 and not hand_playon and not hand2_playon:
				hand_win, hand_reply, hand_playon, hand_draw, hand_payout_bj, player_hand, dealer_hand, deck = bj_player_stand(player_hand = player_hand, dealer_hand = dealer_hand, deck = deck, req = req, split = bj_split, hand1 = True, game_num = game_num, force_dealerReveal = True)
			if bet > 0 and hand_win and not hand_playon and not hand2_playon:
				Logger.log("c","BJ HAND1 Won, bet: %i, bet2: %i" % (bet, bet2))
				hand_winner_tip(req, bet = bet, pot_acct = toacct, winner_acct = acct, token = token, hand_reply = hand_reply, hand_payout_bj = hand_payout_bj)
				bet = 0
				hand_reply = ""
				if bet2 == 0: return
			if bet2 > 0 and hand2_win and not hand_playon and not hand2_playon and game_num == 2:
				Logger.log("c","BJ HAND2 Won, bet: %i, bet2: %i" % (bet, bet2))
				hand_winner_tip(req, bet = bet2, pot_acct = toacct, winner_acct = acct, token = token, hand_reply = hand2_reply, hand_payout_bj = hand2_payout_bj)
				bet2 = 0
				if bet == 0 and bet2 == 0: return
			if (not hand_win or not hand2_win) and (bet > 0 or bet2 > 0):
				Logger.log("c","BJ playon, hand_playon: %s, hand_playon: %s" % (hand_playon, hand2_playon))
				if hand_playon or hand2_playon:
					add_read_timer(nick = req.nick, time = curtime, cmd = "bj", vals = {
						"bj_start":False,
						"game_num":game_num,
						"bj_public":bj_public,
						"deck":deck,
						"dealer_hand":dealer_hand,
						"hand_win":hand_win,
						"hand_draw":hand_draw,
						"player_hand":player_hand,
						"bet":bet,
						"player_hand2":player_hand2,
						"bet2":bet2 })
				elif hand_draw and bet > 0:
					try:
						Transactions.tip(token, toacct, acct, bet, tip_source = "@BLACKJACK") #toacct swapped
						hand_reply = "%s bet returned." % (hand_reply)
					except Transactions.NotEnoughMoney:
						return req.notice_private("Bot ran out of money to return bet!")
				if not hand_playon and not hand2_playon and not hand_draw and choice == "none":
					cancelmsg = bj_cancel(token = token, bot_acct = toacct, player_acct = acct, bet = bet, bet2 = bet2)
					return req.notice_private("%s  %s" % (hand_reply, cancelmsg))
				if len(hand_reply) > 2 and as_notice and req.target not in Config.config["botchannels"] and not bj_public:
					req.notice_private(hand_reply)
				elif len(hand_reply) > 2:
					req.reply(hand_reply)
				if bet2 > 0:
					if hand2_draw:
						try:
							Transactions.tip(token, toacct, acct, bet2, tip_source = "@BLACKJACK") #toacct swapped
							hand2_reply = "%s bet returned." % (hand2_reply)
						except Transactions.NotEnoughMoney:
							return req.notice_private("Bot ran out of money to return bet!")
					if len(hand2_reply) > 2 and as_notice and req.target not in Config.config["botchannels"] and not bj_public:
						req.notice_private(hand2_reply)
					elif len(hand2_reply) > 2:
						req.reply(hand2_reply)
	elif req.nick not in Global.response_read_timers or (req.nick in Global.response_read_timers and Global.response_read_timers[req.nick]["time"] + (5*60) < curtime) or (choice_is_digit != False and choice_is_digit not in choice_digits_accepted):
		try:
			amount = parse_amount(arg[0], acct, min_amount='.0005')
		except ValueError as e:
			return req.notice_private(str(e))
		if req.nick in Global.response_read_timers and Global.response_read_timers[req.nick]["cmd"] == "bj":
			cancelmsg = bj_cancel(token = token, bot_acct = toacct, player_acct = acct, bet = Global.response_read_timers[req.nick]["vals"]["bet"], bet2 = Global.response_read_timers[req.nick]["vals"]["bet2"])
			req.notice_private(cancelmsg)
			Global.response_read_timers.pop(req.nick)
		if amount < minbet:
			return req.reply("Don't be so cheap! %s %s minimum!" % (print_amount(minbet), Config.config["coinab"]), True)
		elif amount > maxbet:
			return req.reply("Sorry, you can only BJ %s %s at a time." % (print_amount(maxbet), Config.config["coinab"]), True)
		if conf_switch == "public":
			bj_public = True
		else:
			bj_public = False
		try:
			Transactions.tip(token, acct, toacct, amount, tip_source = "@BLACKJACK_START")
			add_gamble_timer(targetchannel = req.target, acct = acct, curtime = curtime)
			Global.gamble_list["@HOSTS"][host] = acct
			dealer_hand, player_hand, deck = bj_deal()
			if conf_switch == "auto" and not bj_total(dealer_hand) == 21 and not bj_total(player_hand) == 21:
				as_notice = False
				hand_win, hand_reply, hand_playon, hand_draw, hand_payout_bj, player_hand, dealer_hand, deck = bj_player_auto(player_hand = player_hand, dealer_hand = dealer_hand, deck = deck, req = req, split = False, hand1 = True)
			else:
				hand_win, hand_reply, hand_playon, hand_draw, hand_payout_bj, as_notice = bj_score(req, dealer_hand, player_hand, deal = True)
			if hand_playon:
				add_read_timer(nick = req.nick, time = curtime, cmd = "bj", vals = {
					"bj_start":True,
					"game_num":1,
					"bj_public":bj_public,
					"deck":deck,
					"dealer_hand":dealer_hand,
					"hand_win":False,
					"hand_draw":False,
					"player_hand":player_hand,
					"bet":amount,
					"player_hand2":[],
					"bet2":0 })
			elif hand_win:
				return hand_winner_tip(req, bet = amount, pot_acct = toacct, winner_acct = acct, token = token, hand_reply = hand_reply, hand_payout_bj = hand_payout_bj)
			if as_notice and req.target not in Config.config["botchannels"] and not bj_public:
				return req.notice_private(hand_reply)
			else:
				return req.reply(hand_reply)
		except Transactions.NotEnoughMoney:
			req.notice_private("You tried to play %s %s but you only have %s %s" % (print_amount(amount), Config.config["coinab"], print_amount(Transactions.balance(acct)), Config.config["coinab"]))
			return
	else:
		return req.notice_private("One game at a time!")


def roulette_roll(bet_choice, landon):
	roul_win = False
	odds_str = ""
	roul_multiplier = 0
	red_nums = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
	black_nums = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]
	topline_nums = [0, 1, 2, 3]
	snake_nums = [1, 5, 9, 12, 14, 16, 19, 23, 27, 30, 32, 34]
	col1_nums = [1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34]
	col2_nums = [2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35]
	col3_nums = [3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36]
	s1_nums = [1, 2, 3]
	s2_nums = [4, 5, 6]
	s3_nums = [7, 8, 9]
	s4_nums = [10, 11, 12]
	s5_nums = [13, 14, 15]
	s6_nums = [16, 17, 18]
	s7_nums = [19, 20, 21]
	s8_nums = [22, 23, 24]
	s9_nums = [25, 26, 27]
	s10_nums = [28, 29, 30]
	s11_nums = [31, 32, 33]
	s12_nums = [34, 35, 36]

	if (landon > 0 and landon <= 36 and
		(	(bet_choice == 'even' and landon % 2 == 0) or 
			(bet_choice == 'odd' and landon % 2 == 1) or 
			(bet_choice == 'low' and landon < 19) or 
			(bet_choice == 'high' and landon >= 19) )):
		roul_win = True
		roul_multiplier = 2
		odds_str = "(1to1)"
	elif (landon > 0 and landon <= 36 and
		(	((bet_choice == '1st' or bet_choice == 'first') and landon < 13) or 
			((bet_choice == '2nd' or bet_choice == 'second') and landon >= 13 and landon < 25) or 
			((bet_choice == '3rd' or bet_choice == 'third') and landon >= 25) )):
		roul_win = True
		roul_multiplier = 3
		odds_str = "(2to1)"
	elif (landon > 0 and landon <= 36 and
		(	(bet_choice == 'red' and landon in red_nums) or 
			(bet_choice == 'black' and landon in black_nums) )):
		roul_win = True
		roul_multiplier = 2
		odds_str = "(1to1)"
	elif (	(bet_choice == 'topline' and landon in topline_nums) or 
		(bet_choice == 'basket' and landon in topline_nums)):
		roul_win = True
		roul_multiplier = 9
		odds_str = "(8to1)"
	elif (landon > 0 and
		(	((bet_choice == 'c1' or bet_choice == 'col1') and landon in col1_nums) or
			((bet_choice == 'c2' or bet_choice == 'col2') and landon in col2_nums) or
			((bet_choice == 'c3' or bet_choice == 'col3') and landon in col3_nums) )):
			roul_win = True
			roul_multiplier = 3
			odds_str = "(2to1)"
	elif (landon > 0 and
		(	((bet_choice == 'street1' or bet_choice == 's1') and landon in s1_nums) or
			((bet_choice == 'street2' or bet_choice == 's2') and landon in s2_nums) or
			((bet_choice == 'street3' or bet_choice == 's3') and landon in s3_nums) or
			((bet_choice == 'street4' or bet_choice == 's4') and landon in s4_nums) or
			((bet_choice == 'street5' or bet_choice == 's5') and landon in s5_nums) or
			((bet_choice == 'street6' or bet_choice == 's6') and landon in s6_nums) or
			((bet_choice == 'street7' or bet_choice == 's7') and landon in s7_nums) or
			((bet_choice == 'street8' or bet_choice == 's8') and landon in s8_nums) or
			((bet_choice == 'street9' or bet_choice == 's9') and landon in s9_nums) or
			((bet_choice == 'street10' or bet_choice == 's10') and landon in s10_nums) or
			((bet_choice == 'street11' or bet_choice == 's11') and landon in s11_nums) or
			((bet_choice == 'street12' or bet_choice == 's12') and landon in s12_nums) )):
		roul_win = True
		roul_multiplier = 12
		odds_str = "(11to1)"
	elif (landon > 0 and
		(	bet_choice == 'snake' and landon in snake_nums)):
		roul_win = True
		roul_multiplier = 3
		odds_str = "(2to1)"
	elif bet_choice.isdigit():
		bet_choice_num = int(bet_choice)
		if bet_choice_num >= 0 and bet_choice_num <= 36 and bet_choice_num == landon:
			roul_win = True
			roul_multiplier = 36
			odds_str = "(35to1)"
	return roul_win, roul_multiplier, odds_str


def roulette(req, arg):
	"""%roul <bet_amt1> <bet1> [ <bet_amt2> <bet2> ... ] - Play Roulette with 'bet_amt' and a 'bet'"""
	if len(arg) < 2 or not len(arg) % 2 == 0:
		return req.reply(gethelp("roul"))
	bet_count = len(arg)/2
	acct = Irc.account_names([req.nick])[0]
	host = Irc.get_host(req.source)
	minbet = parse_amount(Config.config["gamble_params"]["@roulette"]["minbet"], min_amount='.0005')
	maxbet = parse_amount(Config.config["gamble_params"]["@roulette"]["maxbet"], min_amount='.0005')
	# if Irc.is_admin(req.source):
	# 	maxbet = 10000
	tempmaxbet = check_gamble_raise(req.nick)
	if tempmaxbet: maxbet = tempmaxbet
	won_bet_count = 0
	lost_bets = 0
	total_bet_amt = 0
	roul_valid_bets = ["even","odd","1st","2nd","3rd","low","high","red","black","topline","snake"]
	roul_bets_help = ["col[1-3]","street[1-12]"]
	roul_valid_bets_aliases = (
		["c1","c2","c3","s1","s2","s3","s4","s5","s6","s7","s8","s9","s10","s11","s12"] +
		["first","second","third","basket","col1","col2","col3","street1","street2","street3","street4","street5","street6","street7","street8","street9","street10","street11","street12"] )
	curtime = time.time()
	random.seed(random_seed_gen())
	# if not Irc.is_admin(req.source):
	# 	return # temporary disable
	if "@HOSTS" not in Global.gamble_list: Global.gamble_list["@HOSTS"] = {}
	user_valid = validate_user(acct, host = host, nick = req.nick, hostlist = Global.gamble_list["@HOSTS"])
	if user_valid != True: return req.notice_private(user_valid)
	if Config.config['maintenance_mode'] and not Irc.is_super_admin(req.source): return req.notice_private("Bot under maintenance.")
	if (req.target == req.nick or req.target not in Config.config["instances"][req.instance]) and not Irc.is_super_admin(req.source):
		return req.reply("Can't roulette in private!")
	timer_vals = Config.config["gamble_params"]["@roulette"]["timers"]
	gamble_timer_reply = check_gamble_timer(instance = req.instance, targetchannel = req.target, cmd_args = arg, nick = req.nick, source = req.source, acct = acct, timers = timer_vals)
	if gamble_timer_reply: return req.reply(gamble_timer_reply)
	toacct = req.instance
	token = Logger.token()
	for i in range(bet_count):
		argoffset = i+i
		bet_choice = arg[(1+argoffset)].lower()
		if bet_choice not in (roul_valid_bets+roul_valid_bets_aliases) and not (bet_choice.isdigit() and int(bet_choice) >= 0 and int(bet_choice) <= 36):
			# return req.reply(gethelp("roul"))
			inval_bet_str = "Invalid bet, available bets: %s or number of choice 0-36" % ((roul_valid_bets+roul_bets_help))
			if req.target not in Config.config["botchannels"]:
				return req.notice_private(inval_bet_str)
			else:
				return req.reply(inval_bet_str)
		try:
			bet = parse_amount(arg[(0+argoffset)], acct, min_amount='.0005')
			arg[(0+argoffset)] = bet
		except ValueError as e:
			return req.notice_private(str(e))
		total_bet_amt = total_bet_amt + bet
	if total_bet_amt < minbet:
		return req.reply("Don't be so cheap! %s %s minimum!" % (print_amount(minbet), Config.config["coinab"]), True)
	elif total_bet_amt > maxbet:
		return req.reply("Sorry, only %s %s at a time." % (print_amount(maxbet), Config.config["coinab"]), True)
	add_gamble_timer(targetchannel = req.target, acct = acct, curtime = curtime)
	Global.gamble_list["@HOSTS"][host] = acct
	roulette_nums = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
	r_red_nums = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
	landon_nums = []
	landon_nums.append(random.choice(roulette_nums))
	rindex = roulette_nums.index(landon_nums[0])
	if rindex == 0: rindex = 37
	landon_nums.append(roulette_nums[rindex-1])
	landon_nums.append(roulette_nums[rindex-2])
	landon = landon_nums[0]
	for x in range(len(landon_nums)):
		if landon_nums[x] in r_red_nums:
			landon_nums[x] = coloured_text(text = str(landon_nums[x]), colour = "04", channel = req.target)
		elif landon_nums[x] == 0:
			landon_nums[x] = coloured_text(text = str(landon_nums[x]), colour = "03", channel = req.target)
		else:
			landon_nums[x] = str(landon_nums[x])
	reply = "Fondling a ball.. [ %s ][ %s ][ %s\x02%s\x02%s ]" % (landon_nums[2], landon_nums[1], coloured_text(text = ">>", colour = "03", channel = req.target), landon_nums[0], coloured_text(text = "<<", colour = "03", channel = req.target))
	try:
		Transactions.tip(token, acct, toacct, total_bet_amt, tip_source = "@ROULETTE_START")
		for i in range(bet_count):
			argoffset = i+i
			bet = arg[(0+argoffset)]
			bet_choice = arg[(1+argoffset)].lower()
			roul_win, roul_multiplier, odds_str = roulette_roll(bet_choice, landon)
			if roul_win:
				won_bet_count = won_bet_count + 1
				roul_winnings = parse_amount(str(bet*roul_multiplier),toacct, roundDown = True, force_no_decimal_calc = True)
				if bet_count > 1 and won_bet_count > 1:
					reply = "%s + %s on %s %s" % (reply, print_amount((roul_winnings-bet)), bet_choice.upper(), odds_str)
				else:
					won_string = "%s %s %s" % (coloured_text(text = "WON", colour = "03", channel = req.target), print_amount((roul_winnings-bet)), coloured_text(text = Config.config["coinab"], colour = "03", channel = req.target))
					reply = "%s ... You %s on %s %s" % (reply, won_string, bet_choice.upper(), odds_str)

				try:
					Transactions.tip(token, toacct, acct, roul_winnings, tip_source = "@ROULETTE_WIN") # accts swapped
				except Transactions.NotEnoughMoney:
					return req.notice_private("%s Bot ran out of winnings!" % (reply))
			else:
				if bet_count > 3:
					lost_bets = lost_bets + bet
				else:
					reply = "%s ... You lost %s %s on %s %s" % (reply, print_amount(bet), Config.config["coinab"], bet_choice.upper(), coloured_text(text = ":<", colour = "04", channel = req.target))
	except Transactions.NotEnoughMoney:
		return req.notice_private("%s You tried to play %s %s but you only have %s %s" % (reply, print_amount(total_bet_amt), Config.config["coinab"], print_amount(Transactions.balance(acct)), Config.config["coinab"]))
	if lost_bets > 0:
		reply = "%s ... You lost %s %s on poor choices %s" % (reply, print_amount(lost_bets), Config.config["coinab"], coloured_text(text = ":<", colour = "04", channel = req.target))
	if won_bet_count > 0:
		reply = "%s%s" % (reply, pot_balance(req.instance))
	return req.reply(reply)


games["lotto"] = lotto
games["lottery"] = lotto
games["gamble"] = lotto

games["bj"] = bj
games["blackjack"] = bj
games["21"] = bj

games["roul"] = roulette
games["roulette"] = roulette
games["ballfondle"] = roulette
games["fondleballs"] = roulette

games["roger-that"] = roger_that




def gethelp(name):
	if name[0] == Config.config["prefix"]:
		name = name[1:]
	cmd = games.get(name, None)
	if cmd and cmd.__doc__:
		return cmd.__doc__.split("\n")[0].replace("%", Config.config["prefix"])
