import logging

from discord.ext import commands

from config import MEME_CHANNEL_ID, TOKEN, REACTION

bot = commands.Bot(command_prefix='!')
logging.basicConfig(filename='eco-memes.log', level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')


@bot.listen('on_ready')
async def on_ready():
    print('Logged in as ' + bot.user.name)
    #TODO run job here


@bot.listen('on_message')
async def on_message(message):
    if message.channel.id != MEME_CHANNEL_ID:
        return
    if message.author.id == bot.user.id:
        return
    if not (message.attachments or message.embeds):
        return
    await message.add_reaction(REACTION)


bot.run(TOKEN)
