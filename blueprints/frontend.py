# -*- coding: utf-8 -*-

__all__ = ()

import bcrypt
import hashlib
import os
import time
import random

from cmyui.logging import Ansi
from cmyui.logging import log
from functools import wraps
from PIL import Image
from pathlib import Path
from quart import Blueprint
from quart import redirect
from quart import render_template
from quart import request
from quart import session
from quart import send_file

from constants import regexes
from objects import glob
from objects import utils
from objects.privileges import Privileges
from objects.utils import flash
from objects.utils import flash_with_customizations
from constants.states import states

VALID_MODES = frozenset({'std', 'taiko', 'catch', 'mania'})
VALID_MODS = frozenset({'vn', 'rx', 'ap'})
UPDATE_IMAGE_COUNTER = [random.randint(0, 7272727272727)]

frontend = Blueprint('frontend', __name__)

def get_img_counter():
    return UPDATE_IMAGE_COUNTER

def login_required(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if not session:
            return await flash('error', 'Você deve estar logado para poder acessar esta página.', 'login')
        return await func(*args, **kwargs)
    return wrapper

@frontend.route('/home')
@frontend.route('/')
async def home():
    return await render_template('home.html')

@frontend.route('/home/account/edit')
async def home_account_edit():
    return redirect('/settings/profile')

@frontend.route('/settings')
@frontend.route('/settings/profile')
@login_required
async def settings_profile():
    return await render_template('settings/profile.html')

@frontend.route('/settings/profile', methods=['POST'])
@login_required
async def settings_profile_post():
    form = await request.form

    new_email = form.get('email', type=str)

    if new_email is None:
        return await flash('error', 'Parâmetros inválidos.', 'home')

    old_email = session['user_data']['email']

    # no data has changed; deny post
    if (new_email == old_email):
        return await flash('error', 'Nenhuma alteração foi feita nos dados.', 'settings/profile')

    if new_email != old_email:
        # Emails must:
        # - match the regex `^[^@\s]{1,200}@[^@\s\.]{1,30}\.[^@\.\s]{1,24}$`
        # - not already be taken by another player
        if not regexes.email.match(new_email):
            return await flash('error', 'A sintaxe do seu novo e-mail está inválida.', 'settings/profile')

        if await glob.db.fetch('SELECT 1 FROM users WHERE email = %s', [new_email]):
            return await flash('error', 'O seu novo e-mail é igual ao de um usuário registrado, escolha outro.', 'settings/profile')

        # email change successful
        await glob.db.execute(
            'UPDATE users '
            'SET email = %s '
            'WHERE id = %s',
            [new_email, session['user_data']['id']]
        )

    # logout
    session.pop('authenticated', None)
    session.pop('user_data', None)
    return await flash('success', 'Your email have been changed! Please login again.', 'login')

@frontend.route('/settings/avatar')
@login_required
async def settings_avatar():
    return await render_template('settings/avatar.html')

@frontend.route('/settings/avatar', methods=['POST'])
@login_required
async def settings_avatar_post():
    # constants
    MAX_IMAGE_SIZE = glob.config.max_image_size * 1024 * 1024
    AVATARS_PATH = f'{glob.config.path_to_gulag}.data/avatars'
    ALLOWED_EXTENSIONS = ['.jpeg', '.jpg', '.png']

    avatar = (await request.files).get('avatar')

    # no file uploaded; deny post
    if avatar is None or not avatar.filename:
        return await flash('error', 'Nenhuma imagem foi selecionada!', 'settings/avatar')

    filename, file_extension = os.path.splitext(avatar.filename.lower())

    # bad file extension; deny post
    if not file_extension in ALLOWED_EXTENSIONS:
        return await flash('error', 'A imagem deve estar no formato de arquivo .JPG, .JPEG, ou .PNG!', 'settings/avatar')
    
    # check file size of avatar
    length = 0
    for i in list(avatar.stream):
        length += len(i)
    if length > MAX_IMAGE_SIZE:
        return await flash('error', 'A imagem que você escolheu é grande demais!', 'settings/avatar')

    # remove old avatars
    for fx in ALLOWED_EXTENSIONS:
        if os.path.isfile(f'{AVATARS_PATH}/{session["user_data"]["id"]}{fx}'): # Checking file e
            os.remove(f'{AVATARS_PATH}/{session["user_data"]["id"]}{fx}')

    # avatar cropping to 1:1
    pilavatar = Image.open(avatar.stream)

    # avatar change success
    pilavatar = utils.crop_image(pilavatar)
    pilavatar.save(os.path.join(AVATARS_PATH, f'{session["user_data"]["id"]}{file_extension.lower()}'))
    UPDATE_IMAGE_COUNTER[0] = random.randint(0, 7272727272727)
    return await flash('success', 'A sua foto de perfil foi alterada com sucesso', 'settings/avatar')

@frontend.route('/settings/custom')
@login_required
async def settings_custom():
    profile_customizations = utils.has_profile_customizations(session['user_data']['id'])
    return await render_template('settings/custom.html', customizations=profile_customizations)

@frontend.route('/settings/custom', methods=['POST'])
@login_required
async def settings_custom_post():
    files = await request.files
    banner = files.get('banner')
    background = files.get('background')
    ALLOWED_EXTENSIONS = ['.jpeg', '.jpg', '.png', '.gif']

    # no file uploaded; deny post
    if banner is None and background is None:
        return await flash_with_customizations('error', 'Nenhuma imagem foi selecionada.', 'settings/custom')

    if banner is not None and banner.filename:
        _, file_extension = os.path.splitext(banner.filename.lower())
        if not file_extension in ALLOWED_EXTENSIONS:
            return await flash_with_customizations('error', f'A imagem do seu novo banner deve estar no formato de arquivo .JPG, .JPEG, ou .PNG!', 'settings/custom')

        banner_file_no_ext = os.path.join(f'.data/banners', f'{session["user_data"]["id"]}')

        # remove old picture
        for ext in ALLOWED_EXTENSIONS:
            banner_file_with_ext = f'{banner_file_no_ext}{ext}'
            if os.path.isfile(banner_file_with_ext):
                os.remove(banner_file_with_ext)

        await banner.save(f'{banner_file_no_ext}{file_extension}')

    if background is not None and background.filename:
        _, file_extension = os.path.splitext(background.filename.lower())
        if not file_extension in ALLOWED_EXTENSIONS:
            return await flash_with_customizations('error', f'A imagem do seu novo papel de parede deve estar no formato de arquivo .JPG, .JPEG, ou .PNG!', 'settings/custom')

        background_file_no_ext = os.path.join(f'.data/backgrounds', f'{session["user_data"]["id"]}')

        # remove old picture
        for ext in ALLOWED_EXTENSIONS:
            background_file_with_ext = f'{background_file_no_ext}{ext}'
            if os.path.isfile(background_file_with_ext):
                os.remove(background_file_with_ext)

        await background.save(f'{background_file_no_ext}{file_extension}')

    UPDATE_IMAGE_COUNTER[0] = random.randint(0, 7272727272727)
    return await flash_with_customizations('success', 'Seu perfil foi customizado com SUCESSO!.', 'settings/custom')


@frontend.route('/settings/password')
@login_required
async def settings_password():
    return await render_template('settings/password.html')

@frontend.route('/settings/password', methods=["POST"])
@login_required
async def settings_password_post():
    form = await request.form
    old_password = form.get('old_password')
    new_password = form.get('new_password')
    repeat_password = form.get('repeat_password')

    # new password and repeat password don't match; deny post
    if new_password != repeat_password:
        return await flash('error', "Sua nova senha não é igual à senha repetida.", 'settings/password')

    # new password and old password match; deny post
    if old_password == new_password:
        return await flash('error', 'Sua senha nova não pode ser igual à senha antiga', 'settings/password')

    # Passwords must:
    # - be within 8-32 characters in length
    # - have more than 3 unique characters
    # - not be in the config's `disallowed_passwords` list
    if not 8 < len(new_password) <= 32:
        return await flash('error', 'A sua nova senha deve ter de 8 a 32 caracteres.', 'settings/password')

    if len(set(new_password)) <= 3:
        return await flash('error', 'Sua nova senha deve conter mais do que 3 caracteres únicos.', 'settings/password')

    if new_password.lower() in glob.config.disallowed_passwords:
        return await flash('error', 'A sua nova senha foi considerada como simples demais.', 'settings/password')

    # cache and other password related information
    bcrypt_cache = glob.cache['bcrypt']
    pw_bcrypt = (await glob.db.fetch(
        'SELECT pw_bcrypt '
        'FROM users '
        'WHERE id = %s',
        [session['user_data']['id']])
    )['pw_bcrypt'].encode()

    pw_md5 = hashlib.md5(old_password.encode()).hexdigest().encode()

    # check old password against db
    # intentionally slow, will cache to speed up
    if pw_bcrypt in bcrypt_cache:
        if pw_md5 != bcrypt_cache[pw_bcrypt]: # ~0.1ms
            if glob.config.debug:
                log(f"{session['user_data']['name']}'s change pw failed - pw incorrect.", Ansi.LYELLOW)
            return await flash('error', 'A sua antiga senha está incorreta.', 'settings/password')
    else: # ~200ms
        if not bcrypt.checkpw(pw_md5, pw_bcrypt):
            if glob.config.debug:
                log(f"{session['user_data']['name']}'s change pw failed - pw incorrect.", Ansi.LYELLOW)
            return await flash('error', 'A sua antiga senha está incorreta.', 'settings/password')

    # remove old password from cache
    if pw_bcrypt in bcrypt_cache:
        del bcrypt_cache[pw_bcrypt]

    # calculate new md5 & bcrypt pw
    pw_md5 = hashlib.md5(new_password.encode()).hexdigest().encode()
    pw_bcrypt = bcrypt.hashpw(pw_md5, bcrypt.gensalt())

    # update password in cache and db
    bcrypt_cache[pw_bcrypt] = pw_md5
    await glob.db.execute(
        'UPDATE users '
        'SET pw_bcrypt = %s '
        'WHERE safe_name = %s',
        [pw_bcrypt, utils.get_safe_name(session['user_data']['name'])]
    )

    # logout
    session.pop('authenticated', None)
    session.pop('user_data', None)
    return await flash('success', 'A sua senha foi alterada! Por favor, faça login novamente.', 'login')


@frontend.route('/u/<id>')
async def profile_select(id):

    mode = request.args.get('mode', 'std', type=str) # 1. key 2. default value
    mods = request.args.get('mods', 'vn', type=str)
    user_data = await glob.db.fetch(
        'SELECT name, safe_name, id, priv, country '
        'FROM users '
        'WHERE safe_name = %s OR id = %s LIMIT 1',
        [utils.get_safe_name(id), id]
    )

    # no user
    if not user_data:
        return (await render_template('404.html'), 404)

    # make sure mode & mods are valid args
    if mode is not None and mode not in VALID_MODES:
        return (await render_template('404.html'), 404)

    if mods is not None and mods not in VALID_MODS:
        return (await render_template('404.html'), 404)

    is_staff = 'authenticated' in session and session['user_data']['is_staff']
    if not user_data or not (user_data['priv'] & Privileges.Normal or is_staff):
        return (await render_template('404.html'), 404)

    user_data['customisation'] = utils.has_profile_customizations(user_data['id'])
    user_data['state_name'] = states[user_data['country'].upper()]
    return await render_template('profile.html', user=user_data, mode=mode, mods=mods)


@frontend.route('/leaderboard')
@frontend.route('/lb')
@frontend.route('/leaderboard/<mode>/<sort>/<mods>')
@frontend.route('/lb/<mode>/<sort>/<mods>')
@frontend.route('/leaderboard/<mode>/<sort>/<mods>/<state>')
@frontend.route('/lb/<mode>/<sort>/<mods>/<state>')
async def leaderboard(mode='std', sort='pp', mods='vn', state='global'):
    return await render_template('leaderboard.html', mode=mode, sort=sort, mods=mods, state=state)

@frontend.route('/beatmaps/<bmId>')
@frontend.route('/beatmapsets/<bmsId>/<mode>/<bmId>')
async def beatmap_page(bmsId = None, mode='std', bmId = None):
    return await render_template('beatmapset.html', bmsId=bmsId, mode=mode, bmId=bmId)

@frontend.route('/login')
async def login():
    if 'authenticated' in session:
        return await flash('error', "Você já está logado.", 'home')

    return await render_template('login.html')

@frontend.route('/login', methods=['POST'])
async def login_post():
    if 'authenticated' in session:
        return await flash('error', "Você já está logado.", 'home')

    if glob.config.debug:
        login_time = time.time_ns()

    form = await request.form
    username = form.get('username', type=str)
    passwd_txt = form.get('password', type=str)

    if username is None or passwd_txt is None:
        return await flash('error', 'Parâmetros inválidos.', 'home')

    # check if account exists
    user_info = await glob.db.fetch(
        'SELECT id, name, email, priv, '
        'pw_bcrypt, silence_end '
        'FROM users '
        'WHERE safe_name = %s',
        [utils.get_safe_name(username)]
    )

    # user doesn't exist; deny post
    # NOTE: Bot isn't a user.
    if not user_info or user_info['id'] == 1:
        if glob.config.debug:
            log(f"{username}'s login failed - account doesn't exist.", Ansi.LYELLOW)
        return await flash('error', 'Conta não existe.', 'login')

    # cache and other related password information
    bcrypt_cache = glob.cache['bcrypt']
    pw_bcrypt = user_info['pw_bcrypt'].encode()
    pw_md5 = hashlib.md5(passwd_txt.encode()).hexdigest().encode()

    # check credentials (password) against db
    # intentionally slow, will cache to speed up
    if pw_bcrypt in bcrypt_cache:
        if pw_md5 != bcrypt_cache[pw_bcrypt]: # ~0.1ms
            if glob.config.debug:
                log(f"{username}'s login failed - pw incorrect.", Ansi.LYELLOW)
            return await flash('error', 'Senha incorreta.', 'login')
    else: # ~200ms
        if not bcrypt.checkpw(pw_md5, pw_bcrypt):
            if glob.config.debug:
                log(f"{username}'s login failed - pw incorrect.", Ansi.LYELLOW)
            return await flash('error', 'Senha incorreta.', 'login')

        # login successful; cache password for next login
        bcrypt_cache[pw_bcrypt] = pw_md5

    # user not verified; render verify
    if not user_info['priv'] & Privileges.Verified:
        if glob.config.debug:
            log(f"{username}'s login failed - not verified.", Ansi.LYELLOW)
        return await render_template('verify.html')

    # user banned; deny post
    if not user_info['priv'] & Privileges.Normal:
        if glob.config.debug:
            log(f"{username}'s login failed - banned.", Ansi.RED)
        return await flash('error', 'Sua conta está restrita. Você não pode fazer login.', 'login')

    # login successful; store session data
    if glob.config.debug:
        log(f"{username}'s login succeeded.", Ansi.LGREEN)

    session['authenticated'] = True
    session['user_data'] = {
        'id': user_info['id'],
        'name': user_info['name'],
        'email': user_info['email'],
        'priv': user_info['priv'],
        'silence_end': user_info['silence_end'],
        'is_staff': user_info['priv'] & Privileges.Staff != 0,
        'is_donator': user_info['priv'] & Privileges.Donator != 0
    }

    if glob.config.debug:
        login_time = (time.time_ns() - login_time) / 1e6
        log(f'Login took {login_time:.2f}ms!', Ansi.LYELLOW)

    return await flash('success', f'Bem-vindo(a) de volta, {username}!', 'home')

@frontend.route('/register')
async def register():
    if 'authenticated' in session:
        return await flash('error', "Você já está logado.", 'home')

    if not glob.config.registration:
        return await flash('error', 'O cadastro está desabilitado.', 'home')

    return await render_template('register.html')

@frontend.route('/register', methods=['POST'])
async def register_post():
    if 'authenticated' in session:
        return await flash('error', "Você já está logado.", 'home')

    if not glob.config.registration:
        return await flash('error', 'O cadastro está desabilitado.', 'home')

    form = await request.form
    username = form.get('username', type=str)
    email = form.get('email', type=str)
    passwd_txt = form.get('password', type=str)
    country = form.get('state', type=str)

    if username is None or email is None or passwd_txt is None or country is None:
        return await flash('error', 'Parâmetros inválidos.', 'register')
    
    key = "7c52a930-f9fe-4346-9b34-69aa431cd72c"
    if glob.config.key_validation:
        key = form.get('key', type=str)
        
        if key is None:
            return await flash('error', 'Parâmetros inválidos.', 'register')
        
        if not regexes.key.match(key):
            return await flash('error', 'Chave de registro inválida.', 'register')
        
        if not await glob.db.fetch('SELECT 1 FROM register_keys WHERE reg_key = %s AND used = 0', key):
            return await flash('error', 'Chave de registro inválida.', 'register')
    
    if glob.config.hCaptcha_sitekey != 'changeme':
        captcha_data = form.get('h-captcha-response', type=str)
        if (
            captcha_data is None or
            not await utils.validate_captcha(captcha_data)
        ):
            return await flash('error', 'Falhou no Captcha.', 'register')

    # Usernames must:
    # - be within 2-15 characters in length
    # - not contain both ' ' and '_', one is fine
    # - not be in the config's `disallowed_names` list
    # - not already be taken by another player
    # check if username exists
    if not regexes.username.match(username):
        return await flash('error', 'A sintaxe do seu nome de usuário está inválida.', 'register')

    if '_' in username and ' ' in username:
        return await flash('error', 'O seu nome de usuário pode conter "_" ou " ", mas não ambos.', 'register')

    if username in glob.config.disallowed_names:
        return await flash('error', 'O seu nome de usuário não é permitido. Por favor, escolha outro.', 'register')

    if await glob.db.fetch('SELECT 1 FROM users WHERE name = %s', username):
        return await flash('error', 'O seu nome de usuário está em uso por algum outro jogador.', 'register')

    # Emails must:
    # - match the regex `^[^@\s]{1,200}@[^@\s\.]{1,30}\.[^@\.\s]{1,24}$`
    # - not already be taken by another player
    if not regexes.email.match(email):
        return await flash('error', 'A sintaxe do seu novo e-mail está inválida.', 'register')

    if await glob.db.fetch('SELECT 1 FROM users WHERE email = %s', email):
        return await flash('error', 'O seu novo e-mail é igual ao de um usuário registrado, escolha outro.', 'register')

    # Passwords must:
    # - be within 8-32 characters in length
    # - have more than 3 unique characters
    # - not be in the config's `disallowed_passwords` list
    if not 8 <= len(passwd_txt) <= 32:
        return await flash('error', 'A sua nova senha deve ter de 8 a 32 caracteres.', 'register')

    if len(set(passwd_txt)) <= 3:
        return await flash('error', 'Sua nova senha deve conter mais do que 3 caracteres únicos.', 'register')

    if passwd_txt.lower() in glob.config.disallowed_passwords:
        return await flash('error', 'A sua nova senha foi considerada como simples demais.', 'register')

    # TODO: add correct locking
    # (start of lock)
    pw_md5 = hashlib.md5(passwd_txt.encode()).hexdigest().encode()
    pw_bcrypt = bcrypt.hashpw(pw_md5, bcrypt.gensalt())
    glob.cache['bcrypt'][pw_bcrypt] = pw_md5 # cache pw

    safe_name = utils.get_safe_name(username)

    # fetch the users' country
    # if (
    #     request.headers and
    #     (ip := request.headers.get('X-Real-IP', type=str)) is not None
    # ):
    #     country = await utils.fetch_geoloc(ip)
    # else:
    #     country = 'xx'

    async with glob.db.pool.acquire() as conn:
        async with conn.cursor() as db_cursor:
            # add to `users` table.
            await db_cursor.execute(
                'INSERT INTO users '
                '(name, safe_name, email, pw_bcrypt, country, creation_time, latest_activity, registered_with_key) '
                'VALUES (%s, %s, %s, %s, %s, UNIX_TIMESTAMP(), UNIX_TIMESTAMP(), %s)',
                [username, safe_name, email, pw_bcrypt, country, key]
            )
            user_id = db_cursor.lastrowid
            
            if glob.config.key_validation:
                await db_cursor.execute(
                    'UPDATE register_keys SET used = 1, user_id_used = %s WHERE reg_key = %s',
                    [user_id, key]
                )

            # add to `stats` table.
            await db_cursor.executemany(
                'INSERT INTO stats '
                '(id, mode) VALUES (%s, %s)',
                [(user_id, mode) for mode in (
                    0,  # vn!std
                    1,  # vn!taiko
                    2,  # vn!catch
                    3,  # vn!mania
                    4,  # rx!std
                    5,  # rx!taiko
                    6,  # rx!catch
                    8,  # ap!std
                )]
            )

    # (end of lock)

    if glob.config.debug:
        log(f'{username} has registered - awaiting verification.', Ansi.LGREEN)

    # user has successfully registered
    return await render_template('verify.html')

@frontend.route('/logout')
async def logout():
    if 'authenticated' not in session:
        return await flash('error', "Você não consegue encerrar sessão se você não está logado!", 'login')

    if glob.config.debug:
        log(f'{session["user_data"]["name"]} logged out.', Ansi.LGREEN)

    # clear session data
    session.pop('authenticated', None)
    session.pop('user_data', None)

    # render login
    return await flash('success', 'Encerrou sessão com sucesso.', 'login')

# social media redirections

@frontend.route('/github')
@frontend.route('/gh')
async def github_redirect():
    return redirect(glob.config.github)

@frontend.route('/discord')
async def discord_redirect():
    return redirect(glob.config.discord_server)

@frontend.route('/youtube')
@frontend.route('/yt')
async def youtube_redirect():
    return redirect(glob.config.youtube)

@frontend.route('/twitter')
async def twitter_redirect():
    return redirect(glob.config.twitter)

@frontend.route('/instagram')
@frontend.route('/ig')
async def instagram_redirect():
    return redirect(glob.config.instagram)

# profile customisation
BANNERS_PATH = Path.cwd() / '.data/banners'
BACKGROUND_PATH = Path.cwd() / '.data/backgrounds'
@frontend.route('/banners/<user_id>')
async def get_profile_banner(user_id: int):
    # Check if avatar exists
    for ext in ('jpg', 'jpeg', 'png', 'gif'):
        path = BANNERS_PATH / f'{user_id}.{ext}'
        if path.exists():
            return await send_file(path)

    return b'{"status":404}'


@frontend.route('/backgrounds/<user_id>')
async def get_profile_background(user_id: int):
    # Check if avatar exists
    for ext in ('jpg', 'jpeg', 'png', 'gif'):
        path = BACKGROUND_PATH / f'{user_id}.{ext}'
        if path.exists():
            return await send_file(path)

    return b'{"status":404}'

@frontend.route('/beatmaps/<beatmap_id>')
@frontend.route('/beatmapsets')
@frontend.route('/beatmapsets/<beatmapset_id>')
@frontend.route('/beatmapsets/<beatmapset_id>/<mode>')
@frontend.route('/beatmapsets/<beatmapset_id>/<mode>/<beatmap_id>')
@frontend.route('/beatmapsets/<beatmapset_id>/<mode>/<beatmap_id>/<extra_mode>')
async def beatmapsets(beatmapset_id: int = None, mode: str = None, beatmap_id: int = None, extra_mode:str = "vn"):
    return await render_template('beatmapset.html', bmsId=beatmapset_id, mode=mode, bmId=beatmap_id, extraMode = extra_mode)
