import sys, os, threading, traceback, time
import theholyrogerrpc, theholyrogerrpc.connection, psycopg2
import Config, Logger, Blocknotify

def database():
	return psycopg2.connect(database = Config.config["database"])

def daemon():
	return theholyrogerrpc.connect_to_local()
JSONRPCException = theholyrogerrpc.proxy.JSONRPCException

cur = database().cursor()
cur.execute("SELECT block FROM lastblock")
lastblock = cur.fetchone()[0]
del cur

class NotEnoughMoney(Exception):
	pass
InsufficientFunds = theholyrogerrpc.exceptions.InsufficientFunds

unconfirmed = {}

# Monkey-patching theholyrogerrpc
def patchedlistsinceblock(self, block_hash, minconf=1):
	try:
		res = self.proxy.listsinceblock(block_hash, minconf)
		res['transactions'] = [theholyrogerrpc.connection.TransactionInfo(**x) for x in res['transactions']]
		return res
	except JSONRPCException as e:
		pass
	except:
		pass

try:
	daemon().listsinceblock("0", 1)
except TypeError:
	theholyrogerrpc.connection.TheHolyRogerConnection.listsinceblock = patchedlistsinceblock
# End of monkey-patching

def txlog(cursor, token, amt, tx = None, address = None, src = None, dest = None):
	cursor.execute("INSERT INTO txlog VALUES (%s, %s, %s, %s, %s, %s, %s)", (time.time(), token, src, dest, amt, tx, address))

def notify_block(): 
	global lastblock, unconfirmed
	lb = daemon().listsinceblock(lastblock, Config.config["confirmations"])
	db = database()
	cur = db.cursor()
	txlist = []
	for tx in lb["transactions"]:
		if tx.category == "receive" and tx.confirmations >= Config.config["confirmations"]:
			txlist.append((int(tx.amount), tx.address, tx.txid.encode("ascii")))
			Logger.log("c","INCOMING: %s %s %s" % (tx.amount, tx.txid.encode("ascii"), tx.address))

	if len(txlist):
		addrlist = [(tx[1],) for tx in txlist]
		# updated to prevent duplicate deposits when bot started before wallet ready by only doing an update if txid doesn't already exist in db
		# Ideally better option is wait until wallet is ready. Maybe getblockcount->getblockhash->getblock->"time" value age old enough?
		cur.executemany("UPDATE accounts SET balance = balance + %s FROM address_account WHERE accounts.account = address_account.account AND address_account.address = %s AND NOT EXISTS (SELECT transaction FROM txlog WHERE transaction = %s)", txlist)
		cur.executemany("UPDATE address_account SET used = '1' WHERE address = %s", addrlist)

	unconfirmed = {}
	for tx in lb["transactions"]:
		if tx.category == "receive":
			cur.execute("SELECT account FROM address_account WHERE address = %s", (tx.address,))
			if cur.rowcount:
				account = cur.fetchone()[0]
				if tx.confirmations < Config.config["confirmations"]:
					unconfirmed[account] = unconfirmed.get(account, 0) + int(tx.amount)
				else:
					txlog(cur, Logger.token(), int(tx.amount), tx = tx.txid.encode("ascii"), address = tx.address, dest = account)

	cur.execute("UPDATE lastblock SET block = %s", (lb["lastblock"],))
	db.commit()
	lastblock = lb["lastblock"]

def balance(account): 
	cur = database().cursor()
	cur.execute("SELECT balance FROM accounts WHERE account = %s", (account,))
	if cur.rowcount:
		return cur.fetchone()[0]
	else:
		return 0

def balance_unconfirmed(account):
	return unconfirmed.get(account, 0)

def check_exists(target): 
	cur = database().cursor()
	cur.execute("SELECT balance FROM accounts WHERE account = %s", (target,))
	if not cur.rowcount:
		return False
	return True


def faucet_board(instance, category = 'jackpot'): 
	cur = database().cursor()
	if category == 'losers':
		cur.execute("SELECT timestamp,destination,amount FROM txlog WHERE source= %s ORDER BY amount ASC, timestamp DESC limit 1", (instance,))
	elif category == 'topwinner':
		cur.execute("SELECT timestamp,destination,amount FROM txlog WHERE source= %s AND amount < 1000 ORDER BY amount DESC, timestamp DESC limit 1", (instance,))
	elif category == 'runnerup1':
		# cur.execute("SELECT timestamp,destination,amount FROM txlog WHERE source= %s AND amount >= 3001 AND amount <= 5000 ORDER BY amount DESC, timestamp DESC limit 1", (instance,))
		cur.execute("SELECT timestamp,destination,amount FROM txlog WHERE source= %s AND amount >= 1000 AND amount <= 2000 ORDER BY timestamp DESC limit 1", (instance,))
	elif category == 'jackpot':
		cur.execute("SELECT timestamp,destination,amount FROM txlog WHERE source= %s AND amount >= 6000 ORDER BY timestamp DESC limit 1", (instance,))
	if cur.rowcount:
		return cur.fetchone()
	else:
		return False

def tip(token, source, target, amount): 
	db = database()
	cur = db.cursor()
	cur.execute("SELECT * FROM accounts WHERE account = ANY(%s) FOR UPDATE", (sorted([target, source]),))
	try:
		cur.execute("UPDATE accounts SET balance = balance - %s WHERE account = %s", (amount, source))
	except psycopg2.IntegrityError as e:
		raise NotEnoughMoney()
	if not cur.rowcount:
		raise NotEnoughMoney()
	cur.execute("UPDATE accounts SET balance = balance + %s WHERE account = %s", (amount, target)) 
	if not cur.rowcount:
		cur.execute("INSERT INTO accounts VALUES (%s, %s)", (target, amount))
	txlog(cur, token, amount, src = source, dest = target)
	db.commit()

def tip_multiple(token, source, dict):
	db = database()
	cur = db.cursor()
	cur.execute("SELECT * FROM accounts WHERE account = ANY(%s) FOR UPDATE", (sorted(dict.keys() + [source]),))
	spent = 0
	for target in dict:
		amount = dict[target]
		try:
			cur.execute("UPDATE accounts SET balance = balance - %s WHERE account = %s", (amount, source))
		except psycopg2.IntegrityError as e:
			raise NotEnoughMoney()
		if not cur.rowcount:
			raise NotEnoughMoney()
		spent += amount
		cur.execute("UPDATE accounts SET balance = balance + %s WHERE account = %s", (amount, target)) 
		if not cur.rowcount:
			cur.execute("INSERT INTO accounts VALUES (%s, %s)", (target, amount))
	for target in dict:
		txlog(cur, token, dict[target], src = source, dest = target)
	db.commit()

def withdraw(token, account, address, amount): 
	db = database()
	cur = db.cursor()
	try:
		cur.execute("UPDATE accounts SET balance = balance - %s WHERE account = %s", (amount + Config.config["txfee"], account))
	except psycopg2.IntegrityError as e:
		raise NotEnoughMoney()
	if not cur.rowcount:
		raise NotEnoughMoney()
	try:
		# Unlock wallet, if applicable
		if Config.config.has_key('walletpassphrase'):
			Logger.log("c","Wallet Unlocked")
			daemon().walletpassphrase(Config.config["walletpassphrase"], 1)

		# Perform transaction
		tx = daemon().sendtoaddress(address, amount, comment = "sent with Rogerer")

		# Lock wallet, if applicable
		if Config.config.has_key('walletpassphrase'):
			Logger.log("c","Wallet Locked")
			daemon().walletlock()

	except InsufficientFunds:
		raise
	except:
		Logger.irclog("Emergency lock on account '%s'" % (account))
		Logger.log("ce","Emergency lock on account '%s'" % (account))
		lock(account, True)
		raise
	db.commit()
	txlog(cur, token, amount + Config.config["txfee"], tx = tx.encode("ascii"), address = address, src = account)
	db.commit()
	return tx.encode("ascii")

def deposit_address(account): 
	db = database()
	cur = db.cursor()
	cur.execute("SELECT address FROM address_account WHERE used = '0' AND account = %s LIMIT 1", (account,))
	if cur.rowcount:
		return cur.fetchone()[0]
	addr = daemon().getnewaddress()
	try:
		cur.execute("SELECT * FROM accounts WHERE account = %s", (account,))
		if not cur.rowcount:
			cur.execute("INSERT INTO accounts VALUES (%s, 0)", (account,))
		cur.execute("INSERT INTO address_account VALUES (%s, %s, '0')", (addr, account))
		db.commit()
	except:
		pass
	return addr.encode("ascii")

def verify_address(address):
	if address.isalnum():
		return daemon().validateaddress(address).isvalid
	else:
		return False

def ping():
	daemon().getbalance()

def balances():
	cur = database().cursor()
	cur.execute("SELECT SUM(balance) FROM accounts")
	db = float(cur.fetchone()[0])
	theholyrogerd = float(daemon().getbalance(minconf = Config.config["confirmations"]))
	return (db, theholyrogerd)

def get_info():
	info = daemon().getinfo()
	return (info, daemon().getblockhash(info.blocks).encode("ascii"))

def get_mining_info():
	info = daemon().getmininginfo()
	return (info, daemon().getblockhash(info.blocks).encode("ascii"))

def get_all_info():
	m_info = daemon().getmininginfo()
	n_info = daemon().getnetworkinfo()
	# allinfo = minfo.copy()
	# allinfo.update(ninfo)
	bestblockhash = daemon().getblockhash(m_info.blocks).encode("ascii")
	return (m_info, n_info, bestblockhash)

def lock(account, state = None):
	if state == None:
		cur = database().cursor()
		cur.execute("SELECT * FROM locked WHERE account = %s", (account,))
		return not not cur.rowcount
	elif state == True:
		db = database()
		cur = db.cursor()
		try:
			cur.execute("INSERT INTO locked VALUES (%s)", (account,))
			db.commit()
		except psycopg2.IntegrityError as e:
			pass
	elif state == False:
		db = database()
		cur = db.cursor()
		cur.execute("DELETE FROM locked WHERE account = %s", (account,))
		db.commit()
