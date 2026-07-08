#include "imubridge.h"
#include <QJsonDocument>
#include <QJsonObject>

ImuBridge::ImuBridge(QObject *parent) : QObject(parent)
{
    m_socket = new QLocalSocket(this);
    m_reconnectTimer = new QTimer(this);
    m_reconnectTimer->setInterval(3000);

    connect(m_socket, &QLocalSocket::readyRead, this, &ImuBridge::onReadyRead);
    connect(m_socket, &QLocalSocket::connected, this, &ImuBridge::onConnected);
    connect(m_socket, &QLocalSocket::disconnected, this, &ImuBridge::onDisconnected);
    connect(m_reconnectTimer, &QTimer::timeout, this, &ImuBridge::tryConnect);

    tryConnect();
    m_reconnectTimer->start();
}

void ImuBridge::connectToImuProcess(const QString &serverName)
{
    m_socket->connectToServer(serverName);
}

void ImuBridge::startAssessment()
{
    if (m_socket->state() == QLocalSocket::ConnectedState)
        m_socket->write("{\"cmd\":\"start_assessment\"}\n");
}

void ImuBridge::stopAssessment()
{
    if (m_socket->state() == QLocalSocket::ConnectedState)
        m_socket->write("{\"cmd\":\"stop_assessment\"}\n");
}

void ImuBridge::onReadyRead()
{
    while (m_socket->canReadLine()) {
        QByteArray line = m_socket->readLine().trimmed();
        QJsonDocument doc = QJsonDocument::fromJson(line);
        if (doc.isObject()) {
            QJsonObject obj = doc.object();
            QMap<QString,double> data;
            for (const QString &key : obj.keys())
                data[key] = obj[key].toDouble();
            emit imuDataReady(data);
        }
    }
}

void ImuBridge::onConnected()
{
    m_connected = true;
    m_reconnectTimer->stop();
    emit connectionChanged(true);
}

void ImuBridge::onDisconnected()
{
    m_connected = false;
    m_reconnectTimer->start();
    emit connectionChanged(false);
}

void ImuBridge::tryConnect()
{
    if (m_socket->state() == QLocalSocket::UnconnectedState)
        m_socket->connectToServer("imu_server");
}
