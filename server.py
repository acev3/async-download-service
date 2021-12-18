from aiohttp import web
import aiofiles
import datetime
import asyncio
import os
import logging
import argparse
from functools import partial


INTERVAL_SECS = 1
logger = logging.getLogger('SERVER')

async def archivate(photos_path, delay, request, kb_step=100):
    archive_hash = request.match_info.get('archive_hash', "hash")
    response = web.StreamResponse()
    response.headers['Content-Disposition'] = f'attachment; filename="photos_{archive_hash}.zip"'
    response.headers['Content-Type'] = 'application/zip'
    folder = os.path.join(photos_path, archive_hash)
    if not os.path.exists(folder):
         return web.HTTPNotFound(
            text='Archive does not exist'
        )
    bytes_step = kb_step * 1024
    await response.prepare(request)
    cmd = 'zip -r - *'
    process = await asyncio.create_subprocess_shell(
        cmd = cmd,
        cwd = folder,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    try:
        while True:
            archive_chank = await process.stdout.read(bytes_step)
            logger.debug('Sending archive chunk ...')
            await response.write(archive_chank)
            await asyncio.sleep(delay)
            if process.stdout.at_eof():
                break
    except asyncio.CancelledError:
        logging.debug('Client was disconnected')
        message = f'Killing process (pid = {str(process.pid)})'
        process.kill()
        await process.communicate()
        logging.debug(message)
    finally:
        logger.debug('Download was interrupted')
        response.force_close()
    return response


async def handle_index_page(request):
    async with aiofiles.open('index.html', mode='r') as index_file:
        index_contents = await index_file.read()
    return web.Response(text=index_contents, content_type='text/html')


async def uptime_handler(request):
    
    response = web.StreamResponse()

    # Большинство браузеров не отрисовывают частично загруженный контент, только если это не HTML.
    # Поэтому отправляем клиенту именно HTML, указываем это в Content-Type.
    response.headers['Content-Type'] = 'text/html'

    # Отправляет клиенту HTTP заголовки
    await response.prepare(request)

    while True:
        formatted_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        message = f'{formatted_date}<br>'  # <br> — HTML тег переноса строки

        # Отправляет клиенту очередную порцию ответа
        await response.write(message.encode('utf-8'))

        await asyncio.sleep(INTERVAL_SECS)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=str, help="Set directory")
    parser.add_argument("--debug", help="Set debug mode")
    parser.add_argument(
        "--delay",
        type=float,
        help="Set delay between chunks",
    )
    args = parser.parse_args()

    if args.debug or os.getenv("DEBUG") == "1":
        logging.basicConfig(level=logging.DEBUG)

    photos_path = args.path or os.getenv("PHOTOS_PATH", "test_photos")
    delay = args.delay or float(os.getenv("DELAY", "0"))

    app = web.Application()
    app.add_routes([
        web.get('/', handle_index_page),
        web.get('/archive/{archive_hash}/', partial(archivate, photos_path, delay)),
    ])
    web.run_app(app)
