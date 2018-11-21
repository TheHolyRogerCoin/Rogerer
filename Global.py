import threading, Queue

active_list = {}
active_lock = threading.Lock()

faucet_list = {}
gamble_list = {}
response_read_timers = {}
welcome_list = {}

instances = {}

ignores = {}
flood_score = {}

account_cache = {}
account_lock = threading.Lock()

whois_lock = threading.Lock()
manager_queue = Queue.Queue()

acctnick_list = {}
nicks_last_shown = {}

svsdata = None
svsevent = None
