# -*- coding: utf-8 -*-
import argparse
import cgi
import os
import shutil
from socketserver import ThreadingMixIn
from urllib.parse import parse_qsl
from wsgiref.simple_server import make_server, WSGIServer

from zipstream import ZipFile


class ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class Application:
    def __init__(self, path):
        self.path = os.path.abspath(path)

    def convert_path(self, path):
        if path.startswith('/'):
            path = path[1:]
        path = os.path.normpath(path)
        if path != '.':
            path = os.path.join(self.path, path)
        else:
            path = self.path
        return path

    def save_files(self, path, files):
        for fs in files:
            if not fs.filename:
                continue
            outfile = os.path.join(path, fs.filename)
            if os.path.exists(outfile):
                raise IOError
            outdir = os.path.dirname(outfile)
            os.makedirs(outdir, exist_ok=True)
            with open(outfile, 'wb') as fout:
                shutil.copyfileobj(fs.file, fout, 100000)

    def generate_success_page(self, path, message):
        html = f"""<html>
    <head>
        <title>{path}</title>
        <meta charset="utf-8"/>
    </head>
    <body>
        <h1>{path}</h1>
        <hr/>
        {message}
        <br/>
        <a href="{path}">Back</a>
        <hr/>
    </body>
</html>
"""
        return html

    def generate_file_list(self, path, filepaths):
        path = str(path)
        if path.endswith('/'):
            path = path[:-1]
        lines = []
        for filepath in filepaths:
            filepath = os.path.basename(filepath)
            href = '/'.join((path, filepath))
            lines.append(f'<p><a href="{href}">{filepath}</a></p>')
        lines = ''.join(lines)
        html = f"""<html>
    <head>
        <title>{path}</title>
        <meta charset="utf-8"/>
    </head>
    <body>
        <h1>{path}</h1>
        <hr/>
        <form enctype="multipart/form-data" action="{path}" method="post">
            <label for="file">Files upload:\t</label>
            <input name="file" type="file" multiple=""/>
            <br/>
            <label for="dfile">Folder upload:\t</label>
            <input name="dfile" type="file" multiple="" directory="" webkitdirectory="" mozdirectory=""/>
            <br/>
            <input type="submit" value="Upload"/>
        </form>
        <hr/>
        <form action="/DownloadAllFiles" method="get">
            <input type="hidden" name="path" value="{path}"/>
            <input type="submit" value="DownloadAllFiles"/>
        </form>
        <hr/>
        {lines}
    </body>
</html>
"""
        return html

    def simple_http_server(self, environ, start_response):
        path = environ['PATH_INFO']
        query = dict(parse_qsl(environ['QUERY_STRING']))
        method = environ["REQUEST_METHOD"]
        fspath = self.convert_path(path)

        if method == "POST":
            post_env = environ.copy()
            post_env['QUERY_STRING'] = ''
            form = cgi.FieldStorage(environ['wsgi.input'],
                                    environ=post_env,
                                    keep_blank_values=True)
            message = "Upload completed successfully."
            try:
                self.save_files(fspath, form.list)
                start_response('200 OK', [])
            except IOError:
                message = "Upload could not be completed. Permission denied?"
                start_response('500 Internal Server Error', [])
            html = self.generate_success_page(path, message).encode()
            yield from [html]
            return

        if path == "/DownloadAllFiles":
            path = self.convert_path(query.setdefault("path", self.path))
            filename = os.path.basename(path)
            status = "200 OK"
            headers = {
                'Content-type': 'application/zip',
                'Content-Disposition':
                    f'attachment; filename="{filename}.zip"'
            }
            start_response(status, list(headers.items()))
            zipfile = ZipFile()
            for root, _, files in os.walk(path):
                arcroot = os.path.relpath(root, path)
                if arcroot == '.':
                    arcroot = ''
                for filename in files:
                    zipfile.write(os.path.join(root, filename),
                                  os.path.join(arcroot, filename))
            yield from zipfile
            return

        if os.path.isfile(fspath):
            start_response('200 OK', [])
            with open(fspath, 'rb') as f:
                yield from f
                return
        elif os.path.isdir(fspath):
            status = "200 OK"
            headers = {}
            filepaths = (x.path for x in os.scandir(fspath))
            html =  self.generate_file_list(path, filepaths).encode()
            start_response(status, list(headers.items()))
            yield from [html]
            return
        else:
            start_response('404 Not Found', [])
            yield from []
            return

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--directory', default=os.getcwd())
    args = parser.parse_args()
    app = Application(args.directory)
    with make_server('', 8000, app.simple_http_server,
                     server_class=ThreadedWSGIServer) as httpd:
        print("Serving on port 8000...")
        httpd.serve_forever()
