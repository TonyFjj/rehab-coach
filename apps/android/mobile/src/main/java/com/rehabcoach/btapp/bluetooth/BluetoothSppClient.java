package com.rehabcoach.btapp.bluetooth;

import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothSocket;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class BluetoothSppClient {
    public static final UUID SPP_UUID =
            UUID.fromString("00001101-0000-1000-8000-00805F9B34FB");
    private static final int MAX_LINE_CHARS = 4 * 1024 * 1024;

    public interface Listener {
        void onConnecting(String deviceName);
        void onConnected(String deviceName);
        void onDisconnected(String reason);
        void onLineReceived(String line);
        void onError(String message, Throwable error);
    }

    private final BluetoothAdapter adapter;
    private final Listener listener;
    private final ExecutorService readExecutor = Executors.newSingleThreadExecutor();
    private final ExecutorService writeExecutor = Executors.newSingleThreadExecutor();
    private final Object writeLock = new Object();

    private BluetoothSocket socket;
    private BufferedWriter writer;
    private volatile boolean running;
    private volatile boolean notifyDisconnect = true;

    public BluetoothSppClient(BluetoothAdapter adapter, Listener listener) {
        this.adapter = adapter;
        this.listener = listener;
    }

    public boolean isConnected() {
        BluetoothSocket current = socket;
        return current != null && current.isConnected();
    }

    public void connect(final BluetoothDevice device) {
        notifyDisconnect = false;
        closeQuietly();
        notifyDisconnect = true;
        readExecutor.execute(new Runnable() {
            @Override
            public void run() {
                String name = safeDeviceName(device);
                listener.onConnecting(name);
                try {
                    cancelDiscoveryQuietly();
                    BluetoothSocket created = openSocket(device);
                    created.connect();
                    socket = created;
                    synchronized (writeLock) {
                        writer = new BufferedWriter(new OutputStreamWriter(
                                created.getOutputStream(), StandardCharsets.UTF_8));
                    }
                    running = true;
                    listener.onConnected(name);
                    readLoop(created);
                } catch (Throwable error) {
                    running = false;
                    closeQuietly();
                    listener.onError("蓝牙连接失败：" + error.getMessage(), error);
                    listener.onDisconnected("连接失败");
                }
            }
        });
    }

    private BluetoothSocket openSocket(BluetoothDevice device) throws IOException {
        IOException lastError = null;

        // RK3588 网关在无 SDP 时固定 RFCOMM channel 1，必须优先走 channel 连接。
        for (int channel : new int[]{1, 2, 3}) {
            try {
                Method insecure = device.getClass().getMethod("createInsecureRfcommSocket", int.class);
                return (BluetoothSocket) insecure.invoke(device, channel);
            } catch (Exception ignored) {
            }
            try {
                Method method = device.getClass().getMethod("createRfcommSocket", int.class);
                return (BluetoothSocket) method.invoke(device, channel);
            } catch (Exception error) {
                lastError = new IOException("RFCOMM channel " + channel + " 失败", error);
            }
        }

        try {
            return device.createInsecureRfcommSocketToServiceRecord(SPP_UUID);
        } catch (IOException error) {
            lastError = error;
        }
        try {
            return device.createRfcommSocketToServiceRecord(SPP_UUID);
        } catch (IOException error) {
            lastError = error;
        }
        if (lastError != null) {
            throw lastError;
        }
        throw new IOException("无法创建 RFCOMM 连接");
    }

    public void sendLine(final String line) {
        writeExecutor.execute(new Runnable() {
            @Override
            public void run() {
                synchronized (writeLock) {
                    if (writer == null || socket == null || !socket.isConnected()) {
                        listener.onError("尚未连接蓝牙服务", null);
                        return;
                    }
                    try {
                        writer.write(line);
                        if (!line.endsWith("\n")) {
                            writer.write("\n");
                        }
                        writer.flush();
                    } catch (IOException error) {
                        listener.onError("蓝牙发送失败：" + error.getMessage(), error);
                        disconnect("发送失败");
                    }
                }
            }
        });
    }

    public void disconnect(String reason) {
        running = false;
        closeQuietly();
        if (notifyDisconnect) {
            listener.onDisconnected(reason == null ? "已断开" : reason);
        }
    }

    public void shutdown() {
        disconnect("退出应用");
        readExecutor.shutdownNow();
        writeExecutor.shutdownNow();
    }

    private void readLoop(BluetoothSocket activeSocket) {
        try {
            java.io.InputStream rawIn = activeSocket.getInputStream();
            StringBuilder pending = new StringBuilder();
            byte[] buf = new byte[8192];
            int read;
            while (running && (read = rawIn.read(buf)) != -1) {
                pending.append(new String(buf, 0, read, StandardCharsets.UTF_8));
                int newline;
                while ((newline = indexOfNewline(pending)) >= 0) {
                    String line = pending.substring(0, newline).trim();
                    pending.delete(0, newline + 1);
                    if (line.length() > MAX_LINE_CHARS) {
                        listener.onError("蓝牙消息过大，已跳过", null);
                        continue;
                    }
                    if (!line.isEmpty()) {
                        listener.onLineReceived(line);
                    }
                }
                if (pending.length() > MAX_LINE_CHARS) {
                    pending.setLength(0);
                    listener.onError("蓝牙缓冲区溢出，已重置", null);
                }
            }
            if (running) {
                listener.onDisconnected("对端已断开");
            }
        } catch (IOException error) {
            if (running) {
                listener.onError("蓝牙接收失败：" + error.getMessage(), error);
                listener.onDisconnected("接收失败");
            }
        } finally {
            running = false;
            closeQuietly();
        }
    }

    private static int indexOfNewline(StringBuilder builder) {
        for (int i = 0; i < builder.length(); i++) {
            if (builder.charAt(i) == '\n') {
                return i;
            }
        }
        return -1;
    }

    private void cancelDiscoveryQuietly() {
        try {
            if (adapter != null && adapter.isDiscovering()) {
                adapter.cancelDiscovery();
            }
        } catch (SecurityException ignored) {
        }
    }

    private void closeQuietly() {
        synchronized (writeLock) {
            BufferedWriter currentWriter = writer;
            writer = null;
            if (currentWriter != null) {
                try {
                    currentWriter.close();
                } catch (IOException ignored) {
                }
            }
            BluetoothSocket currentSocket = socket;
            socket = null;
            if (currentSocket != null) {
                try {
                    currentSocket.close();
                } catch (IOException ignored) {
                }
            }
        }
    }

    private String safeDeviceName(BluetoothDevice device) {
        try {
            String name = device.getName();
            if (name != null && !name.trim().isEmpty()) {
                return name;
            }
        } catch (SecurityException ignored) {
        }
        return device.getAddress();
    }
}
