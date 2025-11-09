#!/usr/bin/env python3
"""
GUI interface for Nest Yale Lock testing and control.

Provides both web-based (Flask) and desktop (Tkinter) options.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

try:
    from flask import Flask, render_template_string, jsonify, request
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext, messagebox
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False

from nest_tool import (
    GetSessionWithAuth,
    _observe_stream,
    _send_lock_command,
    EnhancedProtobufHandler,
    NestProtobufHandler,
    _build_observe_payload
)


# Web-based GUI (Flask)
if FLASK_AVAILABLE:
    app = Flask(__name__)
    
    HTML_TEMPLATE = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Nest Yale Lock Control</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
                background: #f5f5f5;
            }
            .container {
                background: white;
                border-radius: 8px;
                padding: 20px;
                margin-bottom: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            h1 { color: #333; }
            h2 { color: #666; margin-top: 0; }
            button {
                background: #4285f4;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
                margin: 5px;
            }
            button:hover { background: #357ae8; }
            button:disabled { background: #ccc; cursor: not-allowed; }
            .status { padding: 10px; margin: 10px 0; border-radius: 4px; }
            .status.success { background: #d4edda; color: #155724; }
            .status.error { background: #f8d7da; color: #721c24; }
            .status.info { background: #d1ecf1; color: #0c5460; }
            .lock-info {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 10px;
                margin: 10px 0;
            }
            .lock-card {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 15px;
                background: #f9f9f9;
            }
            .trait-list {
                max-height: 400px;
                overflow-y: auto;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 10px;
            }
            .trait-item {
                padding: 8px;
                margin: 5px 0;
                background: #f0f0f0;
                border-radius: 4px;
            }
            .trait-item.decoded { border-left: 4px solid #28a745; }
            .trait-item.not-decoded { border-left: 4px solid #ffc107; }
            pre {
                background: #f4f4f4;
                padding: 10px;
                border-radius: 4px;
                overflow-x: auto;
            }
            .loading { display: none; }
            .loading.active { display: inline-block; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔒 Nest Yale Lock Control</h1>
            <div id="status"></div>
        </div>
        
        <div class="container">
            <h2>Lock Control</h2>
            <div id="locks-container"></div>
            <button onclick="refreshLocks()">🔄 Refresh Status</button>
            <button onclick="lockDevice()">🔒 Lock</button>
            <button onclick="unlockDevice()">🔓 Unlock</button>
        </div>
        
        <div class="container">
            <h2>Trait Decoder</h2>
            <button onclick="decodeTraits()">📊 Decode All Traits</button>
            <div id="traits-container"></div>
        </div>
        
        <script>
            let currentDeviceId = null;
            let sessionData = null;
            
            async function refreshLocks() {
                showStatus('Loading lock status...', 'info');
                try {
                    const response = await fetch('/api/locks');
                    const data = await response.json();
                    sessionData = data;
                    displayLocks(data);
                    showStatus('Lock status refreshed', 'success');
                } catch (error) {
                    showStatus('Error: ' + error.message, 'error');
                }
            }
            
            function displayLocks(data) {
                const container = document.getElementById('locks-container');
                const locks = data.yale || {};
                
                if (Object.keys(locks).length === 0) {
                    container.innerHTML = '<p>No locks found</p>';
                    return;
                }
                
                let html = '<div class="lock-info">';
                for (const [deviceId, lockInfo] of Object.entries(locks)) {
                    if (!currentDeviceId) currentDeviceId = deviceId;
                    const isLocked = lockInfo.bolt_locked ? '🔒 Locked' : '🔓 Unlocked';
                    const isMoving = lockInfo.bolt_moving ? ' (Moving)' : '';
                    html += `
                        <div class="lock-card">
                            <h3>${deviceId}</h3>
                            <p><strong>Status:</strong> ${isLocked}${isMoving}</p>
                            <p><strong>Actuator State:</strong> ${lockInfo.actuator_state || 'N/A'}</p>
                            <button onclick="selectDevice('${deviceId}')">Select</button>
                        </div>
                    `;
                }
                html += '</div>';
                container.innerHTML = html;
            }
            
            function selectDevice(deviceId) {
                currentDeviceId = deviceId;
                showStatus(`Selected device: ${deviceId}`, 'info');
            }
            
            async function lockDevice() {
                if (!currentDeviceId) {
                    showStatus('Please select a device first', 'error');
                    return;
                }
                await sendCommand('lock');
            }
            
            async function unlockDevice() {
                if (!currentDeviceId) {
                    showStatus('Please select a device first', 'error');
                    return;
                }
                await sendCommand('unlock');
            }
            
            async function sendCommand(action) {
                showStatus(`Sending ${action} command...`, 'info');
                try {
                    const response = await fetch(`/api/command`, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            device_id: currentDeviceId,
                            action: action
                        })
                    });
                    const data = await response.json();
                    if (data.success) {
                        showStatus(`Command sent successfully`, 'success');
                        setTimeout(refreshLocks, 1000);
                    } else {
                        showStatus('Error: ' + data.error, 'error');
                    }
                } catch (error) {
                    showStatus('Error: ' + error.message, 'error');
                }
            }
            
            async function decodeTraits() {
                showStatus('Decoding traits...', 'info');
                try {
                    const response = await fetch('/api/decode');
                    const data = await response.json();
                    displayTraits(data);
                    showStatus('Traits decoded successfully', 'success');
                } catch (error) {
                    showStatus('Error: ' + error.message, 'error');
                }
            }
            
            function displayTraits(data) {
                const container = document.getElementById('traits-container');
                const allTraits = data.all_traits || {};
                
                if (Object.keys(allTraits).length === 0) {
                    container.innerHTML = '<p>No traits found</p>';
                    return;
                }
                
                let html = '<div class="trait-list">';
                for (const [traitKey, traitInfo] of Object.entries(allTraits)) {
                    const [objId, typeUrl] = traitKey.split(':', 2);
                    const traitName = typeUrl.split('.').pop() || typeUrl;
                    const decoded = traitInfo.decoded;
                    const data = traitInfo.data || {};
                    
                    html += `
                        <div class="trait-item ${decoded ? 'decoded' : 'not-decoded'}">
                            <strong>${traitName}</strong> ${decoded ? '✅' : '⚠️'}
                            <br><small>Object: ${objId || 'N/A'}</small>
                            ${decoded && Object.keys(data).length > 0 ? 
                                '<pre>' + JSON.stringify(data, null, 2) + '</pre>' : 
                                '<p>Not decoded</p>'}
                        </div>
                    `;
                }
                html += '</div>';
                container.innerHTML = html;
            }
            
            function showStatus(message, type) {
                const statusDiv = document.getElementById('status');
                statusDiv.className = 'status ' + type;
                statusDiv.textContent = message;
            }
            
            // Auto-refresh on load
            window.onload = refreshLocks;
        </script>
    </body>
    </html>
    """
    
    @app.route('/')
    def index():
        return render_template_string(HTML_TEMPLATE)
    
    @app.route('/api/locks')
    def api_locks():
        try:
            session, access_token, user_id, transport_url = GetSessionWithAuth()
            handler = NestProtobufHandler()
            locks_data, _ = asyncio.run(_observe_stream(session, access_token, transport_url, handler))
            session.close()
            return jsonify(locks_data)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/decode')
    def api_decode():
        try:
            session, access_token, user_id, transport_url = GetSessionWithAuth()
            handler = EnhancedProtobufHandler()
            locks_data, _ = asyncio.run(_observe_stream(session, access_token, transport_url, handler, max_messages=5))
            session.close()
            return jsonify(locks_data)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/command', methods=['POST'])
    def api_command():
        try:
            data = request.json
            device_id = data.get('device_id')
            action = data.get('action')
            
            if not device_id or not action:
                return jsonify({'success': False, 'error': 'Missing device_id or action'}), 400
            
            session, access_token, user_id, transport_url = GetSessionWithAuth()
            handler = NestProtobufHandler()
            locks_data, observe_base = asyncio.run(_observe_stream(session, access_token, transport_url, handler))
            
            response = _send_lock_command(
                session, access_token, device_id,
                locks_data.get('user_id') or user_id,
                locks_data.get('structure_id'),
                action, observe_base, transport_url, dry_run=False
            )
            session.close()
            
            return jsonify({'success': True, 'response': str(response)})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


# Desktop GUI (Tkinter)
if TKINTER_AVAILABLE:
    class NestLockGUI:
        def __init__(self, root):
            self.root = root
            self.root.title("Nest Yale Lock Control")
            self.root.geometry("800x600")
            
            # Create notebook for tabs
            notebook = ttk.Notebook(root)
            notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # Lock Control Tab
            lock_frame = ttk.Frame(notebook)
            notebook.add(lock_frame, text="Lock Control")
            self.setup_lock_tab(lock_frame)
            
            # Trait Decoder Tab
            decode_frame = ttk.Frame(notebook)
            notebook.add(decode_frame, text="Trait Decoder")
            self.setup_decode_tab(decode_frame)
            
            self.current_device_id = None
            self.session_data = None
        
        def setup_lock_tab(self, parent):
            # Status frame
            status_frame = ttk.LabelFrame(parent, text="Status", padding=10)
            status_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            self.status_label = ttk.Label(status_frame, text="Ready")
            self.status_label.pack()
            
            # Locks frame
            locks_frame = ttk.LabelFrame(parent, text="Locks", padding=10)
            locks_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            self.locks_text = scrolledtext.ScrolledText(locks_frame, height=10, width=70)
            self.locks_text.pack(fill=tk.BOTH, expand=True)
            
            # Buttons
            button_frame = ttk.Frame(parent)
            button_frame.pack(fill=tk.X, padx=10, pady=10)
            
            ttk.Button(button_frame, text="Refresh Status", command=self.refresh_locks).pack(side=tk.LEFT, padx=5)
            ttk.Button(button_frame, text="Lock", command=lambda: self.send_command('lock')).pack(side=tk.LEFT, padx=5)
            ttk.Button(button_frame, text="Unlock", command=lambda: self.send_command('unlock')).pack(side=tk.LEFT, padx=5)
        
        def setup_decode_tab(self, parent):
            # Traits frame
            traits_frame = ttk.LabelFrame(parent, text="Decoded Traits", padding=10)
            traits_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            self.traits_text = scrolledtext.ScrolledText(traits_frame, height=20, width=70)
            self.traits_text.pack(fill=tk.BOTH, expand=True)
            
            # Button
            button_frame = ttk.Frame(parent)
            button_frame.pack(fill=tk.X, padx=10, pady=10)
            
            ttk.Button(button_frame, text="Decode All Traits", command=self.decode_traits).pack(side=tk.LEFT, padx=5)
        
        def refresh_locks(self):
            self.status_label.config(text="Loading...")
            self.root.update()
            
            try:
                session, access_token, user_id, transport_url = GetSessionWithAuth()
                handler = NestProtobufHandler()
                locks_data, _ = asyncio.run(_observe_stream(session, access_token, transport_url, handler))
                session.close()
                
                self.session_data = locks_data
                locks = locks_data.get('yale', {})
                
                self.locks_text.delete(1.0, tk.END)
                if locks:
                    for device_id, lock_info in locks.items():
                        if not self.current_device_id:
                            self.current_device_id = device_id
                        status = "🔒 Locked" if lock_info.get('bolt_locked') else "🔓 Unlocked"
                        moving = " (Moving)" if lock_info.get('bolt_moving') else ""
                        self.locks_text.insert(tk.END, f"{device_id}: {status}{moving}\n")
                        self.locks_text.insert(tk.END, f"  Actuator State: {lock_info.get('actuator_state', 'N/A')}\n\n")
                else:
                    self.locks_text.insert(tk.END, "No locks found\n")
                
                self.status_label.config(text="Status refreshed")
            except Exception as e:
                self.status_label.config(text=f"Error: {e}")
                messagebox.showerror("Error", str(e))
        
        def send_command(self, action):
            if not self.current_device_id:
                messagebox.showwarning("Warning", "Please refresh locks first")
                return
            
            self.status_label.config(text=f"Sending {action} command...")
            self.root.update()
            
            try:
                session, access_token, user_id, transport_url = GetSessionWithAuth()
                handler = NestProtobufHandler()
                locks_data, observe_base = asyncio.run(_observe_stream(session, access_token, transport_url, handler))
                
                response = _send_lock_command(
                    session, access_token, self.current_device_id,
                    locks_data.get('user_id') or user_id,
                    locks_data.get('structure_id'),
                    action, observe_base, transport_url, dry_run=False
                )
                session.close()
                
                self.status_label.config(text=f"{action.capitalize()} command sent")
                messagebox.showinfo("Success", f"{action.capitalize()} command sent successfully")
                self.refresh_locks()
            except Exception as e:
                self.status_label.config(text=f"Error: {e}")
                messagebox.showerror("Error", str(e))
        
        def decode_traits(self):
            self.traits_text.delete(1.0, tk.END)
            self.traits_text.insert(tk.END, "Decoding traits...\n")
            self.root.update()
            
            try:
                session, access_token, user_id, transport_url = GetSessionWithAuth()
                handler = EnhancedProtobufHandler()
                locks_data, _ = asyncio.run(_observe_stream(session, access_token, transport_url, handler, max_messages=5))
                session.close()
                
                all_traits = locks_data.get('all_traits', {})
                self.traits_text.delete(1.0, tk.END)
                
                if all_traits:
                    for trait_key, trait_info in sorted(all_traits.items()):
                        obj_id, type_url = trait_key.split(':', 1) if ':' in trait_key else (None, trait_key)
                        trait_name = type_url.split('.').pop() if '.' in type_url else type_url
                        decoded = trait_info.get('decoded', False)
                        data = trait_info.get('data', {})
                        
                        status = "✅" if decoded else "⚠️"
                        self.traits_text.insert(tk.END, f"{status} {trait_name}\n")
                        if obj_id:
                            self.traits_text.insert(tk.END, f"  Object: {obj_id}\n")
                        if decoded and data:
                            self.traits_text.insert(tk.END, f"  Data: {json.dumps(data, indent=2)}\n")
                        self.traits_text.insert(tk.END, "\n")
                else:
                    self.traits_text.insert(tk.END, "No traits found\n")
            except Exception as e:
                self.traits_text.insert(tk.END, f"Error: {e}\n")
                messagebox.showerror("Error", str(e))


def main():
    parser = argparse.ArgumentParser(description="GUI interface for Nest Yale Lock")
    parser.add_argument(
        '--mode',
        choices=['web', 'desktop'],
        default='desktop' if TKINTER_AVAILABLE else 'web',
        help='GUI mode (default: desktop if available, else web)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=5000,
        help='Port for web GUI (default: 5000)'
    )
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='Host for web GUI (default: 127.0.0.1)'
    )
    
    args = parser.parse_args()
    
    if args.mode == 'web':
        if not FLASK_AVAILABLE:
            print("Error: Flask is required for web GUI. Install with: pip install flask", file=sys.stderr)
            return 1
        print(f"Starting web GUI at http://{args.host}:{args.port}", file=sys.stderr)
        app.run(host=args.host, port=args.port, debug=False)
    else:
        if not TKINTER_AVAILABLE:
            print("Error: Tkinter is required for desktop GUI.", file=sys.stderr)
            print("On Linux, install with: sudo apt-get install python3-tk", file=sys.stderr)
            return 1
        root = tk.Tk()
        app_gui = NestLockGUI(root)
        root.mainloop()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

