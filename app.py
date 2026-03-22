#!/usr/bin/env python3
"""
imapsync Web UI - A modern web interface for imapsync
"""

import os
import re
import json
import uuid
import shutil
import subprocess
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response, stream_with_context

app = Flask(__name__)

# In-memory job store
jobs = {}

def find_imapsync():
    """Find imapsync binary."""
    # Check common locations
    for path in ["imapsync", "/usr/bin/imapsync", "/usr/local/bin/imapsync"]:
        if shutil.which(path):
            return path
    return None

def build_command(params):
    """Build imapsync command from form parameters."""
    cmd = ["imapsync"]

    # Host 1
    if params.get("host1"):
        cmd += ["--host1", params["host1"]]
    if params.get("port1"):
        cmd += ["--port1", params["port1"]]
    if params.get("user1"):
        cmd += ["--user1", params["user1"]]
    if params.get("password1"):
        cmd += ["--password1", params["password1"]]
    if params.get("ssl1") == "true":
        cmd += ["--ssl1"]
    if params.get("tls1") == "true":
        cmd += ["--tls1"]

    # Host 2
    if params.get("host2"):
        cmd += ["--host2", params["host2"]]
    if params.get("port2"):
        cmd += ["--port2", params["port2"]]
    if params.get("user2"):
        cmd += ["--user2", params["user2"]]
    if params.get("password2"):
        cmd += ["--password2", params["password2"]]
    if params.get("ssl2") == "true":
        cmd += ["--ssl2"]
    if params.get("tls2") == "true":
        cmd += ["--tls2"]

    # Options
    if params.get("dry_run") == "true":
        cmd += ["--dry"]
    if params.get("delete2") == "true":
        cmd += ["--delete2"]
    if params.get("expunge1") == "true":
        cmd += ["--expunge1"]
    if params.get("expunge2") == "true":
        cmd += ["--expunge2"]
    if params.get("subscribe") == "true":
        cmd += ["--subscribe"]
    if params.get("noauthmd5") == "true":
        cmd += ["--noauthmd5"]
    if params.get("exclude"):
        cmd += ["--exclude", params["exclude"]]
    if params.get("include"):
        cmd += ["--include", params["include"]]
    if params.get("folder"):
        cmd += ["--folder", params["folder"]]
    if params.get("maxsize"):
        cmd += ["--maxsize", params["maxsize"]]
    if params.get("maxage"):
        cmd += ["--maxage", params["maxage"]]
    if params.get("search"):
        cmd += ["--search", params["search"]]

    # Suppress slow folder-size scans; --nolog keeps the container filesystem
    # clean since the web UI captures all output via stdout.
    # NOTE: imapsync auto-enables --nolog in Docker anyway, but we keep it
    # explicit. The CGI env-var scrub in run_sync() is the real fix that
    # prevents imapsync from entering CGI mode under gunicorn.
    cmd += ["--nofoldersizes", "--nofoldersizesatend", "--nolog"]

    return cmd

def run_sync(job_id, params):
    """Run imapsync and stream output to job store."""
    job = jobs[job_id]
    job["status"] = "running"
    job["started_at"] = datetime.now().isoformat()
    job["output"] = []
    job["stats"] = {
        "messages_transferred": 0,
        "messages_skipped": 0,
        "bytes_transferred": 0,
        "folders": 0,
        "errors": 0,
    }

    imapsync = find_imapsync()
    if not imapsync:
        job["status"] = "error"
        job["output"].append({
            "type": "error",
            "text": "imapsync not found. Please install imapsync first.",
            "ts": datetime.now().isoformat()
        })
        return

    cmd = build_command(params)
    job["command"] = " ".join(cmd)

    try:
        # Build a clean environment for imapsync.
        # imapsync checks for CGI-related env vars (SERVER_SOFTWARE, GATEWAY_INTERFACE,
        # REQUEST_METHOD, HTTP_*, etc.) to decide whether it is being invoked as a CGI
        # script. When gunicorn is running, those vars leak into child processes and
        # trick imapsync into CGI mode -- which causes it to emit HTTP headers, switch
        # log behaviour, run only a "justconnect" probe, and then exit.
        # Solution: pass a clean copy of os.environ with every CGI/HTTP key stripped.
        CGI_VARS = {
            "GATEWAY_INTERFACE", "SERVER_SOFTWARE", "SERVER_NAME", "SERVER_PORT",
            "SERVER_PROTOCOL", "REQUEST_METHOD", "REQUEST_URI", "PATH_INFO",
            "PATH_TRANSLATED", "SCRIPT_NAME", "SCRIPT_FILENAME", "QUERY_STRING",
            "REMOTE_ADDR", "REMOTE_HOST", "REMOTE_PORT", "REMOTE_USER",
            "AUTH_TYPE", "CONTENT_TYPE", "CONTENT_LENGTH",
        }
        clean_env = {
            k: v for k, v in os.environ.items()
            if k not in CGI_VARS and not k.startswith("HTTP_")
        }

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=clean_env,
        )
        job["pid"] = process.pid

        for line in process.stdout:
            line = line.rstrip()
            if not line:
                continue

            # Classify line
            line_type = "info"
            if re.search(r"error|failed|failure|cannot|could not", line, re.I):
                line_type = "error"
                job["stats"]["errors"] += 1
            elif re.search(r"warning|warn", line, re.I):
                line_type = "warning"
            elif re.search(r"Transfer\s+\d+", line, re.I) or "msg" in line.lower():
                line_type = "transfer"
                # Try to extract message count
                m = re.search(r"(\d+)\s+msg", line)
                if m:
                    job["stats"]["messages_transferred"] = int(m.group(1))
            elif re.search(r"Folder", line, re.I):
                line_type = "folder"
                job["stats"]["folders"] += 1
            elif re.search(r"Skipping", line, re.I):
                line_type = "skip"
                job["stats"]["messages_skipped"] += 1
            elif re.search(r"Bytes", line, re.I):
                m = re.search(r"(\d+)\s+bytes", line)
                if m:
                    job["stats"]["bytes_transferred"] = int(m.group(1))

            job["output"].append({
                "type": line_type,
                "text": line,
                "ts": datetime.now().isoformat()
            })

        process.wait()
        job["exit_code"] = process.returncode
        job["status"] = "completed" if process.returncode == 0 else "failed"

    except Exception as e:
        job["status"] = "error"
        job["output"].append({
            "type": "error",
            "text": str(e),
            "ts": datetime.now().isoformat()
        })
    finally:
        job["ended_at"] = datetime.now().isoformat()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/sync", methods=["POST"])
def start_sync():
    params = request.json
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "created_at": datetime.now().isoformat(),
        "params": {k: v for k, v in params.items() if k not in ("password1", "password2")},
        "output": [],
        "stats": {}
    }
    thread = threading.Thread(target=run_sync, args=(job_id, params), daemon=True)
    thread.start()
    return jsonify({"job_id": job_id})


@app.route("/api/jobs")
def list_jobs():
    return jsonify([
        {k: v for k, v in job.items() if k != "output"}
        for job in sorted(jobs.values(), key=lambda x: x["created_at"], reverse=True)
    ])


@app.route("/api/jobs/<job_id>")
def get_job(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Not found"}), 404
    since = int(request.args.get("since", 0))
    result = {k: v for k, v in job.items() if k != "output"}
    result["output"] = job["output"][since:]
    result["output_total"] = len(job["output"])
    return jsonify(result)


@app.route("/api/jobs/<job_id>/stop", methods=["POST"])
def stop_job(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Not found"}), 404
    pid = job.get("pid")
    if pid:
        try:
            import signal
            os.kill(pid, signal.SIGTERM)
            job["status"] = "stopped"
        except ProcessLookupError:
            pass
    return jsonify({"ok": True})


@app.route("/api/check")
def check_imapsync():
    path = find_imapsync()
    if path:
        try:
            result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            version = result.stdout.strip() or result.stderr.strip()
            return jsonify({"available": True, "path": path, "version": version[:200]})
        except Exception as e:
            return jsonify({"available": True, "path": path, "version": "unknown"})
    return jsonify({"available": False})


if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)
