#include "llmbridge.h"
#include <QJsonDocument>
#include <QJsonObject>

LlmBridge::LlmBridge(QObject *parent) : QObject(parent)
{
    m_socket = new QLocalSocket(this);
    m_reconnectTimer = new QTimer(this);
    m_reconnectTimer->setInterval(3000);
    connect(m_socket, &QLocalSocket::readyRead, this, &LlmBridge::onReadyRead);
    connect(m_socket, &QLocalSocket::connected, this, &LlmBridge::onConnected);
    connect(m_socket, &QLocalSocket::disconnected, this, &LlmBridge::onDisconnected);
    connect(m_reconnectTimer, &QTimer::timeout, this, &LlmBridge::tryConnect);
    tryConnect(); m_reconnectTimer->start();
}

void LlmBridge::requestGuidance(const QString &actionName, double angleError, const QString &phase)
{
    if (m_socket->state() != QLocalSocket::ConnectedState) return;
    QJsonObject req;
    req["action"] = actionName;
    req["error"] = angleError;
    req["phase"] = phase;
    m_socket->write(QJsonDocument(req).toJson(QJsonDocument::Compact) + "\n");
}

void LlmBridge::onReadyRead()
{
    while (m_socket->canReadLine()) {
        QByteArray line = m_socket->readLine().trimmed();
        QJsonDocument doc = QJsonDocument::fromJson(line);
        if (doc.isObject())
            emit guidanceReady(doc.object()["text"].toString());
    }
}

void LlmBridge::onConnected() { m_reconnectTimer->stop(); emit connectionChanged(true); }
void LlmBridge::onDisconnected() { m_reconnectTimer->start(); emit connectionChanged(false); }
void LlmBridge::tryConnect() {
    if (m_socket->state() == QLocalSocket::UnconnectedState)
        m_socket->connectToServer("llm_server");
}
