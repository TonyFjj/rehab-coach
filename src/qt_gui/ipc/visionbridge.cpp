#include "visionbridge.h"
#include <QJsonDocument>
#include <QJsonArray>

VisionBridge::VisionBridge(QObject *parent) : QObject(parent)
{
    m_socket = new QLocalSocket(this);
    m_reconnectTimer = new QTimer(this);
    m_reconnectTimer->setInterval(3000);
    connect(m_socket, &QLocalSocket::readyRead, this, &VisionBridge::onReadyRead);
    connect(m_socket, &QLocalSocket::connected, this, &VisionBridge::onConnected);
    connect(m_socket, &QLocalSocket::disconnected, this, &VisionBridge::onDisconnected);
    connect(m_reconnectTimer, &QTimer::timeout, this, &VisionBridge::tryConnect);
    tryConnect(); m_reconnectTimer->start();
}

void VisionBridge::startCapture()
{
    if (m_socket->state() == QLocalSocket::ConnectedState)
        m_socket->write("{\"cmd\":\"start_capture\"}\n");
}

void VisionBridge::stopCapture()
{
    if (m_socket->state() == QLocalSocket::ConnectedState)
        m_socket->write("{\"cmd\":\"stop_capture\"}\n");
}

void VisionBridge::onReadyRead()
{
    while (m_socket->canReadLine()) {
        QByteArray line = m_socket->readLine().trimmed();
        QJsonDocument doc = QJsonDocument::fromJson(line);
        if (!doc.isObject()) continue;
        Skeleton3D skel;
        skel.timestamp = doc.object()["timestamp"].toVariant().toLongLong();
        QJsonArray arr = doc.object()["joints"].toArray();
        for (const QJsonValue &v : arr) {
            QJsonArray p = v.toArray();
            skel.joints.append(QVector3D(p[0].toDouble(), p[1].toDouble(), p[2].toDouble()));
        }
        emit skeletonReady(skel);
    }
}

void VisionBridge::onConnected() { m_reconnectTimer->stop(); emit connectionChanged(true); }
void VisionBridge::onDisconnected() { m_reconnectTimer->start(); emit connectionChanged(false); }
void VisionBridge::tryConnect() {
    if (m_socket->state() == QLocalSocket::UnconnectedState)
        m_socket->connectToServer("vision_server");
}
