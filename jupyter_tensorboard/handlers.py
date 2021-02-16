# -*- coding: utf-8 -*-
# Copyright (c) 2017-2019, Shengpeng Liu.  All rights reserved.
# Copyright (c) 2019, Alex Ford.  All rights reserved.
# Copyright (c) 2020-2021, NVIDIA CORPORATION. All rights reserved.

from tornado import web
from tornado.wsgi import WSGIContainer
from notebook.base.handlers import IPythonHandler
from notebook.utils import url_path_join as ujoin
from notebook.base.handlers import path_regex

notebook_dir = None

def load_jupyter_server_extension(nb_app):

    global notebook_dir
    # notebook_dir should be root_dir of contents_manager
    notebook_dir = nb_app.contents_manager.root_dir

    web_app = nb_app.web_app
    base_url = web_app.settings['base_url']

    try:
        from .tensorboard_manager import manager
    except ImportError:
        nb_app.log.info("import tensorboard error, check tensorflow install")
        handlers = [
            (ujoin(
                base_url, r"/tensorboard.*"),
                TensorboardErrorHandler),
        ]
    else:
        web_app.settings["tensorboard_manager"] = manager
        from . import api_handlers

        handlers = [
            (ujoin(
                base_url, r"/tensorboard/(?P<name>\w+)%s" % path_regex),
                TensorboardHandler),
            (ujoin(
                base_url, r"/api/tensorboard"),
                api_handlers.TbRootHandler),
            (ujoin(
                base_url, r"/api/tensorboard/(?P<name>\w+)"),
                api_handlers.TbInstanceHandler),
            (ujoin(
                base_url, r"/font-roboto/.*"),
                TbFontHandler),
        ]

    web_app.add_handlers('.*$', handlers)
    nb_app.log.info("jupyter_tensorboard extension loaded.")


class TensorboardHandler(IPythonHandler):

    def _impl(self, name, path):

        self.request.path = path

        manager = self.settings["tensorboard_manager"]
        if name in manager:
            tb_app = manager[name].tb_app
            WSGIContainer(tb_app)(self.request)
        else:
            raise web.HTTPError(404)

    @web.authenticated
    def get(self, name, path):

        if path == "":
            uri = self.request.path + "/"
            if self.request.query:
                uri += "?" + self.request.query
            self.redirect(uri, permanent=True)
            return

        if self.get_cookie("_xsrf"):
            self.set_cookie("XSRF-TOKEN", self.get_cookie("_xsrf"))

        self._impl(name, path)

    @web.authenticated
    def post(self, name, path):

        if path == "":
            raise web.HTTPError(403)

        self._impl(name, path)

    def check_xsrf_cookie(self):
        """Expand XSRF check exceptions for POST requests.

        For TensorBoard versions <= 2.4.x, expand check_xsrf_cookie exceptions,
        normally only applied to GET and HEAD requests, to POST requests
        for TensorBoard API calls, as TensorBoard doesn't return back the
        header used for XSRF checks.

        Provides support for TensorBoard plugins that use POST to retrieve
        experiment information.

        """

        # Set our own expectations as to whether TB will implement this
        # See https://github.com/tensorflow/tensorboard/issues/4685
        # Presently assuming TB > 2.4 will fix this
        from distutils.version import LooseVersion
        import tensorboard as tb
        tb_has_xsrf = (LooseVersion(tb.__version__) >= LooseVersion("2.5"))

        # Check whether any XSRF token is provided
        req_has_xsrf = (self.get_argument("_xsrf", None)
                or self.request.headers.get("X-Xsrftoken")
                or self.request.headers.get("X-Csrftoken"))

        # If applicable, translate Angular's XSRF header to Tornado's name
        if (self.request.headers.get("X-XSRF-TOKEN") and not req_has_xsrf):

            self.request.headers.add("X-Xsrftoken",
                    self.request.headers.get("X-XSRF-TOKEN"))

            req_has_xsrf = True


        # Check XSRF token
        try:
            return super(TensorboardHandler, self).check_xsrf_cookie()

        except web.HTTPError:
            # Note: GET and HEAD exceptions are already handled in
            # IPythonHandler.check_xsrf_cookie and will not normally throw 403

            # If the request had one of the XSRF tokens, or if TB > 2.4.x,
            # then no exceptions, and we're done
            if req_has_xsrf or tb_has_xsrf:
                raise

            # Otherwise, we must loosen our expectations a bit.  IPythonHandler
            # has some existing exceptions to consider a matching Referer as
            # sufficient for GET and HEAD requests; we extend that here to POST
            # for TB versions <= 2.4.x that don't handle XSRF tokens

            if self.request.method in {"POST"}:
                # Consider Referer a sufficient cross-origin check, mirroring
                # logic in IPythonHandler.check_xsrf_cookie.
                if not self.check_referer():
                    referer = self.request.headers.get("Referer")
                    if referer:
                        msg = (
                            "Blocking Cross Origin request from {}."
                            .format(referer)
                        )
                    else:
                        msg = "Blocking request from unknown origin"
                    raise web.HTTPError(403, msg)
            else:
                raise


class TbFontHandler(IPythonHandler):

    @web.authenticated
    def get(self):
        manager = self.settings["tensorboard_manager"]
        if "1" in manager:
            tb_app = manager["1"].tb_app
            WSGIContainer(tb_app)(self.request)
        else:
            raise web.HTTPError(404)


class TensorboardErrorHandler(IPythonHandler):
    pass
