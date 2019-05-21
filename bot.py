# Work with Python 3.6
# Discord v. 0.16.12
# Encoding UTF-8
#
# Invite
# https://discordapp.com/api/oauth2/authorize?client_id=540100510708006912&permissions=490688&scope=bot
#
# Usefull links:
# https://www.devdungeon.com/content/make-discord-bot-python-part-2
# https://discordpy.readthedocs.io/en/latest/api.html?highlight=react#user
#
# TODO:
# * (optional) Add selection_line creation regex (%emoji | %answer %answer %answer %answer %answer | %answer %answer | %nickname)
# * (optional) Change handle commads from .startswith() to switch or other cleaner code
# * !FIX help message
# * add !plan clean answers - remove all answers from last plan
# 
# * run and debug [ongoing]
#
# TO DEBUG:
# * nick, emoji / default, normal - on different severs, channels
#

import discord
import pickle
import asyncio
import traceback

# GLOBAL VARIABLES
BOT_PREFIX = ("!")
# Didn't expect for that server can be accesed with just token
# Didn't really cared for bot to be broken
client = discord.Client(command_prefix=BOT_PREFIX)

# defaultAnswers = ['🔢', '✅', '❌', '❔', '😒', '🎲', '↩'] # all, yes, no, idk, maybe, dice, cancel
defaultAnswers = ['🔢', '✅', '❌', '❔', '😒', '↩'] # all, yes, no, idk, maybe, cancel
# emptyAnswers = ['🔢', '↩'] # all, cancel - could be used as default answers
emojiNr = ['1⃣' ,'2⃣' ,'3⃣' ,'4⃣' ,'5⃣' ,'6⃣' ,'7⃣' ,'8⃣' ,'9⃣', '🔢'] #{[1]-[9], [1234]}
emojiAll = '🔢'
emojiClear = '↩'
defaultEmoji = '👤'
defaultPlanSize = 7
planCasheSize = 5
pickleDataDelay = 5
pinMessage = False
plans = {} # { [channel.id] : Plan }
globalUsers = [] # [ PlanUser, ... ]

# PLAN CLASSES

class PlanUser():
    def __init__(self, user, selection = [], answers = None, emoji = None, serverEmoji = {}, serverNickname = {}):
        print("__init__user", user.id, serverEmoji, serverNickname, selection)
        self.user = user
        if emoji == None:
            self.emoji = defaultEmoji
        else:
            self.emoji = emoji
        self.selection = selection
        self.serverEmoji = serverEmoji
        self.serverNickname = serverNickname
        if answers == None:
            self.answers = emojiNr.copy()
        else:
            self.answers = answers

    def __eq__(self, other):
        """Overrides the default implementation"""
        if isinstance(other, PlanUser):
            return self.user.id == other.user.id
        if isinstance(other, discord.User):
            return self.user.id == other.id
        return False

    def copy(self):
        print("copy()", self.user.id)
        return PlanUser(self.user, self.selection.copy(), self.answers.copy(), self.emoji, self.serverEmoji, self.serverNickname)

class Plan():
    def __init__(self, message, text, size):
        print("__init__plan")
        self.message = message
        self.text = text
        self.size = size
        self.answers = defaultAnswers.copy()
        self.users = []
        pass

    def __eq__(self, other):
        """Overrides the default implementation"""
        if isinstance(other, Plan) or isinstance(other, discord.Reaction):
            return self.message.id == other.message.id
        elif isinstance(other, discord.Message):
            return self.message.id == other.id
        return False

    def to_msg(self):
        print("to_msg")
        # [any text]
        # [emoji][answers]        [nickname] [selection]
        #  \[T]/  1 2 3 4 5 | 6 7  user.nick  2 3 4
        msg = self.text + " \n"
        for user in self.users:
            print("server:", self.message.server.id, "nick:", user.serverNickname, "name:", user.user.display_name, "id:", user.user.id, "emoji:", user.serverEmoji)
            # use channel emoji if set
            if self.message.server.id in user.serverEmoji:
                msg += user.serverEmoji[self.message.server.id]
            else:
                msg += user.emoji
            msg += " "*4
            div = 0
            # add answers
            for answer in user.answers:
                if div == 5:
                    msg += "|"
                div += 1
                msg += emoji_snowflake(answer) + " "
            # use channel nickname if set
            if self.message.server.id in user.serverNickname:
                msg += user.serverNickname[self.message.server.id] + " "
            else:
                msg += user.user.display_name + " "
            # add selection
            for selected in user.selection:
                msg += emoji_snowflake(selected) + " "
            msg += "\n"
        return msg

    async def handlereaction(self, reaction, user, flag = False):
        print("handlereaction")
        # print('Debug:', reaction, emoji_name(reaction.emoji)) #Debug
        # Get user / Add to global
        #for user1 in self.users: print(user1.user.id, user1.serverNickname, user1.serverEmoji)
        user = (await get_user(user, reaction.message.server.id)).copy()
        #print(user.user.id, user.serverNickname, user.serverEmoji)
        if user not in self.users:
            user.answers = emojiNr[0:self.size]
            self.users.append(user)
        #print(2)
        #for user2 in self.users: print(user2.user.id, user2.serverNickname, user2.serverEmoji)
        #print(3)
        userIdx = self.users.index(user)
        #print(4, userIdx)
        user = self.users[userIdx]
        #print(5, user.user.id)
        # Handle reaction
        emoji = emoji_name(reaction.emoji)
        if emoji in emojiNr[0:self.size]: # Add selection
            self._handle_selection(user, emoji, flag)
        else:
            if (emoji not in self.answers) and (reaction.emoji in self.answers): # Add answer
                self.answers.append(reaction.emoji)
            if not flag:
                self._add_answer(user, reaction.emoji)
        #update plan message
        await self.refresh_plan()
        await save_backup()
        pass

    def _add_answer(self, user, emoji):
        print("_add_answer")
        userId = self.users.index(user)
        emojiName = emoji_name(emoji)
        if emojiName == emojiAll: # Select all
            self.users[userId].selection = emojiNr[0:self.size]
            return
        elif emojiName == emojiClear: # Clear selection
            self.users[userId].selection = []
            return
        else: # Answer
            for selected in self.users[userId].selection:
                index = emojiNr.index(selected)
                self.users[userId].answers[index] = emoji
            self.users[userId].selection = []
        pass

    def _handle_selection(self, user, emoji, removed):
        print("_handle_selection")
        userId = self.users.index(user)
        selection = self.users[userId].selection
        if (not removed) and (emoji not in self.users[userId].selection):
            selection.append(emoji)
            selection = selection.sort()
        elif removed and (emoji in self.users[userId].selection):
            selection.remove(emoji)
        pass

    async def refresh_plan(self):
        print("refresh_plan")
        msg = self.to_msg()
        await client.edit_message(self.message, msg)

    async def send_plan(self):
        print("send_plan")
        # resend plan
        msg = self.to_msg()
        self.message = await client.send_message(self.message.channel, msg)
        if pinMessage:
            await client.pin_message(self.message)
        # recreate plan
        for e in emojiNr[0:self.size]:
            await client.add_reaction(self.message, e)
        for e in self.answers:
            await client.add_reaction(self.message, e)
        await save_backup()
        pass

    async def resend_plan(self):
        # if pinMessage:
            # await client.unpin_message(self.message)
        await client.delete_message(self.message)
        await self.send_plan()
        pass

    async def update_text(self, text):
        print("update_text")
        self.text = text
        await self.refresh_plan()
        pass


# ===================== BACKUP ============================
backupOngoing = False
backupFileName = 'planner.backup'

class Backup():
    def __init__(self, users, plans):
        self.users = users.copy()
        self.plans = plans.copy()
        pass

async def save_backup():
    print("save_backup")
    global backupOngoing
    global globalUsers
    global plans
    if not backupOngoing:
        print("save_to_file_wait")
        backupOngoing = True
        # wait 5 sec before creating backup
        # trying to prevent too many and unnecessary file operations
        await asyncio.sleep(pickleDataDelay)
        print("save_to_file_start")
        bp = Backup(globalUsers, plans)
        fileHandler = open(backupFileName, 'wb+')
        pickle.dump(bp, fileHandler)
        backupOngoing = False
        print("save_to_file_end")
    print("save_backup_end")
    return

async def load_backup():
    print("load_backup")
    global globalUsers
    global plans
    try:
        fileHandler = open(backupFileName, 'rb+')
    except:
        #no file to load
        await save_backup()
        return
    dump = pickle.load(fileHandler)
    globalUsers = dump.users
    plans = dump.plans
    return

# =========================================================
# ===================== EVENTS ============================
# =========================================================
#DONE
@client.event
async def on_reaction_add(reaction, user):
    #print("on_reaction_add")
    await on_reaction(reaction, user, False)

@client.event
async def on_reaction_remove(reaction, user):
    #print("on_reaction_remove")
    await on_reaction(reaction, user, True)

async def on_reaction(reaction, user, removed = False):
    global plans
    # we do not want the bot to reply to itself
    if user == client.user:
        return
    try_plan(reaction.message.channel)
    try:
        planIdx = plans[reaction.message.channel.id].index(reaction)
    except:
        #print("Reaction not on followed message")
        return;
    print("- - - - - - - - - - - - - - - -")
    print("on_reaction", removed)
    await plans[reaction.message.channel.id][planIdx].handlereaction(reaction, user, removed)

@client.event
async def on_message(message):
    #TODO move command to struct, add help function
    # we do not want the bot to reply to itself
    if message.author == client.user:
        return

    # return if not command
    if not message.content[0] in BOT_PREFIX:
        return

    print("=========== START ==============")
    # print("on_message", message.content)
    print("on_message")
    global pinMessage
    try_plan(message.channel)

    # handle commands
    if message.content.startswith("!plan"):
        #remove len("!plan ")
        message.content = message.content[6:]
        if message.content.startswith("new"):
            message.content = message.content[4:]
    # !plan new size
            if message.content.startswith("size "):
                message.content = message.content[5:]
                await plan_new_size(message, int(message.content[0:1]), message.content[2:])
    # !plan new
            else: # !plan new
                await plan_new(message, message.content)
    # !plan edit last
        # elif message.content.startswith("edit last "):
            # message.content = message.content[10:]
            # await plan_edit_last(message.channel, message.content)
    # !plan edit (same as '!plan edit last')
        elif message.content.startswith("edit "):
            message.content = message.content[5:]
            await plan_edit_last(message.channel, message.content)
    # !plan at
        #elif message.content.startswith("at "):
            #message.content = message.content[3:]
            #await resend_plan_at(message.channel, int(message.content[0:1]))
        else:
    # !plan
            await resend_plan_at(message.channel)
    elif message.content.startswith("!set "):
        message.content = message.content[5:]
        if message.content.startswith("nick "):
            message.content = message.content[5:]
    # !set nick
            await set_nick(message, message.content)
        elif message.content.startswith("emoji "):
            message.content = message.content[6:]
            if message.content.startswith("default "):
    # !set emoji default
                message.content = message.content[8:]
                await set_emoji(message, message.content, True)
    # !set emoji
            else:
                await set_emoji(message, message.content)
    # !set plan default size
    # elif message.content.startswith("!set plan default size "):
        # need to be possible to handle it per server/channel instead of globally
        # message.content = message.content[23:]
    # !pin (need to be done per server))
    #elif message.content.startswith("!pin "):
    #    message.content = message.content[6:]
    #    if message.content.startswith("y") or message.content.startswith("yes"):
    #        pinMessage = True
    #    elif message.content.startswith("n") or message.content.startswith("no"):
    #        pinMessage = False
    # !help answers
    elif message.content.startswith("!help answers"):
        #defaultAnswers = ['🔢', '✅', '❌', '❔', '😒', '↩'] # all, yes, no, idk, maybe, dice, cancel
        msg = 'Each plan comes with default answers:'
        msg += '  ✅ - yes, "I agree".'
        msg += '  ❌ - no, "I disagree".'
        msg += '  ❔ - no answer right now, "I may know later."'
        msg += '  😒 - yes, BUT "I dont fully agree".'
        await client.send_message(message.channel, msg)
    # !help usage
    elif message.content.startswith("!help usage"):
        msg = 'PlannerBot functionality:'
        msg += ' * user is added to plan after selecting (adding reaction) option in bot message.'
        msg += ' * select numbers from emojis (adding reaction), to pick them (from 1 to [plan size]). They will be displayed next to your nickname as selected.'
        msg += ' * select \'🔢\' to select all numbers.'
        msg += ' * select ↩ to clear all selected numbers'
        msg += ' * select other (or new) emoji to set it as your answer'
        await client.send_message(message.channel, msg)
    # !help
    elif message.content.startswith("!help"):
        # msg = "!plan [|new [\"msg\"|size [1-9] \"msg\"]|edit last|]\n!set [nick|emoji [|default]]\n!help"
        msg = "Available commands:"
        msg += "!help - this message"
        msg += "\n!help usage - explanation of bot interface"
        msg += "\n!help aswers - explanation of meanning of default answers"
        # msg += "\n!pin message [y/yes/n/no]] - choose if plan should be pinned in channel (default [n/no])"
        msg += "\n!plan - resend last plan"
        msg += '\n!plan new [any test] - create plan with default size of {0} and text [any text]'.format(defaultPlanSize)
        msg += '\n!plan new size [size] [any test] - create plan with size of [size] (value from 1-9) and text [any text]'
        msg += '\n!plan edit [any text] - change text from last plan to new [any text]'
        # msg += '\n!plan edit last [any text] - change text from last plan to new [any text]'
        # msg += '!\nplan at [number] - resend plan [number] from last (starting with 1). Limit per channel {0}'.format(planCasheSize)
        msg += "\n!set nick [any text] - set your nickname to [any text] in this server"
        #msg += "\n!set nick default [any text] - set your nickname to [any text] for all servers with this bot"
        msg += "\n!set emoji [any text] - set your emoji to [any text] in this server"
        msg += "\n!set emoji default [any text] - set your emoji to [any text] for all servers with this bot"
        await client.send_message(message.channel, msg)
    else:
        print("Unknown command:", message.content)
    print("=========== END ================")

# =========================================================
# ===================== COMMANDS ==========================
# =========================================================
def try_plan(channel):
    try:
        plans[channel.id]
    except:
        plans[channel.id] = []

async def plan(channel, idx = -1):
    print("plan")
    global plans
    if (idx < -1) or (idx >= len(plans)):
        return
    await plans[channel.id][idx].send_plan()

async def plan_new(message, text):
    print("plan_new")
        #!plan_new size [size 1-9] [text...]
    await plan_new_size(message, defaultPlanSize, text)

async def plan_new_size(message, size, text):
    print("plan_new_size")
    global plans
    #!plan new size [text...]
    if len(plans[message.channel.id]) >= planCasheSize:
        plans[message.channel.id].pop(0)
    plans[message.channel.id].append(Plan(message, text, size))
    await plan(message.channel)

async def _plan_edit(channel, idx, text):
    print("_plan_edit")
    #!plan edit [text...]
    await plans[channel.id][-idx].update_text(text)

async def plan_edit_last(channel, text):
    print("plan_edit_last")
    #!plan edit [text...]
    await _plan_edit(channel, 1, text)

async def resend_plan_at(channel, idx = 1):
    await plans[channel.id][-idx].resend_plan()

async def get_user(user, serverId):
    print("get_user", user.display_name, user.id)
    global globalUsers
    try:
        userIdx = globalUsers.index(user)
        print("user exist", userIdx)
        #if serverId not in globalUsers[userIdx].serverNickname:
        #    globalUsers[userIdx].serverNickname[serverId] = user.display_name
        user = globalUsers[userIdx]
    except:
        print("new user")
        user = PlanUser(user, [], None, None, {}, {})
        #user.serverNickname[serverId] = user.user.display_name
        #user.emoji = defaultEmoji
        #for user1 in globalUsers: print(user1.user.id, user1.serverNickname, user1.serverEmoji)
        globalUsers.append(user) # Add global user
        #for user2 in globalUsers: print(user2.user.id, user2.serverNickname, user2.serverEmoji)
    return user

async def set_nick(message, text):
    print("set_nick")
    user = await get_user(message.author, message.server.id)
    user.serverNickname[message.server.id] = text

    for s in plans:
        if(message.server.id != s):
            continue
        for p in plans[s]:
            try:
                userId = p.users.index(user)
                p.users[userId].nickname = text
            except:
                print("Exception in set_nick:\n", traceback.format_exc())

async def set_emoji(message, emoji, default = False):
    print("set_emoji")
    user = await get_user(message.author, message.server.id)
    print(default, user.serverEmoji, message.server.id)
    if(default):
        user.emoji = emoji
    else:
        user.serverEmoji[message.server.id] = emoji

    for s in plans:
        if((not default) and (message.server.id != s)):
            continue
        for p in plans[s]:
            try:
                userId = p.users.index(user)
                p.users[userId].emoji = emoji
            except:
                print("Exception in set_emoji:\n", traceback.format_exc())

def emoji_name(emoji):
    if isinstance(emoji, discord.Emoji):
        return emoji.name
    else:
        return emoji

def emoji_snowflake(emoji):
    return str(emoji)

# async def reload_messages():
    # await plan[-1].resend_plan()

# ========================= OTHERS =============================
@client.event
async def on_ready():
    print('---------------------')
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('---------------------')
    print('Load backup -- START')
    await load_backup()
    print('Load backup -- FINISHED')
    # in discord v. 1.0 there could be used on_raw_reaction.
    #   Without it, we can't catch events before bot start/restart
    # Need to resend messages to catch events for them
    #   But it would be stupid to resend on all channels conected with bot
    # Better to do it manually with !plan
    #print('Reload plan messages -- START')
    #await reload_messages()
    #print('Reload plan messages -- FINISHED')
    print('---------------------')
    print('------- READY -------')
    print('---------------------')

client.run(TOKEN)

