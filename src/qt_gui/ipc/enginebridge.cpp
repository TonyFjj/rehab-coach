#include "enginebridge.h"

#include <QLocalSocket>
#include <QTcpSocket>
#include <QAbstractSocket>
#include <QJsonDocument>
#include <QJsonArray>
#include <QDateTime>

namespace {
const char kEngineUnixPath[] = "/tmp/rehab_engine.sock";
const char kEngineTcpHost[] = "127.0.0.1";
const quint16 kEngineTcpPort = 9002;
}

EngineBridge::EngineBridge(QObject *parent)
    : QObject(parent)
{
#if defined(Q_OS_LINUX) || defined(Q_OS_UNIX)
    m_useLocalSocket = true;
#endif

    setupSocket();

    m_reconnectTimer = new QTimer(this);
    m_reconnectTimer->setInterval(3000);
    connect(m_reconnectTimer, &QTimer::timeout, this, &EngineBridge::tryConnect);

    connectEngine();
}

EngineBridge::~EngineBridge() = default;

void EngineBridge::setupSocket()
{
    if (m_useLocalSocket) {
        m_localSocket = new QLocalSocket(this);
        connect(m_localSocket, &QLocalSocket::connected, this, &EngineBridge::onConnected);
        connect(m_localSocket, &QLocalSocket::disconnected, this, &EngineBridge::onDisconnected);
        connect(m_localSocket, &QLocalSocket::readyRead, this, &EngineBridge::onReadyRead);
        return;
    }

    m_tcpSocket = new QTcpSocket(this);
    connect(m_tcpSocket, &QTcpSocket::connected, this, &EngineBridge::onConnected);
    connect(m_tcpSocket, &QTcpSocket::disconnected, this, &EngineBridge::onDisconnected);
    connect(m_tcpSocket, &QTcpSocket::readyRead, this, &EngineBridge::onReadyRead);
}

QIODevice *EngineBridge::device() const
{
    if (m_useLocalSocket) {
        return m_localSocket;
    }
    return m_tcpSocket;
}

bool EngineBridge::isSocketConnected() const
{
    if (m_useLocalSocket && m_localSocket) {
        return m_localSocket->state() == QLocalSocket::ConnectedState;
    }
    if (m_tcpSocket) {
        return m_tcpSocket->state() == QAbstractSocket::ConnectedState;
    }
    return false;
}

void EngineBridge::connectEngine()
{
    tryConnect();
    if (!m_reconnectTimer->isActive()) {
        m_reconnectTimer->start();
    }
}

bool EngineBridge::isConnected() const
{
    return m_connected;
}

void EngineBridge::tryConnect()
{
    if (m_useLocalSocket && m_localSocket) {
        if (m_localSocket->state() == QLocalSocket::ConnectedState ||
            m_localSocket->state() == QLocalSocket::ConnectingState) {
            return;
        }
        m_localSocket->connectToServer(QString::fromUtf8(kEngineUnixPath));
        return;
    }
    if (m_tcpSocket) {
        if (m_tcpSocket->state() == QAbstractSocket::ConnectedState ||
            m_tcpSocket->state() == QAbstractSocket::ConnectingState) {
            return;
        }
        m_tcpSocket->connectToHost(QString::fromUtf8(kEngineTcpHost), kEngineTcpPort);
    }
}

void EngineBridge::sendCommand(
    const QString &command,
    const QJsonObject &extra)
{
    if (!isConnected()) {
        m_pendingCommand = command;
        m_pendingExtra = extra;
        tryConnect();
        return;
    }

    QJsonObject payload = extra;
    payload.insert(QStringLiteral("command"), command);

    QJsonObject msg;
    msg.insert(QStringLiteral("type"), QStringLiteral("command"));
    msg.insert(
        QStringLiteral("timestamp"),
        QDateTime::currentMSecsSinceEpoch() / 1000.0);
    msg.insert(QStringLiteral("payload"), payload);
    writeLine(msg);
}

void EngineBridge::writeLine(const QJsonObject &obj)
{
    QIODevice *io = device();
    if (!io || !isSocketConnected()) {
        return;
    }
    const QByteArray line =
        QJsonDocument(obj).toJson(QJsonDocument::Compact) + '\n';
    io->write(line);
}

void EngineBridge::onConnected()
{
    m_connected = true;
    m_reconnectTimer->stop();
    emit connectionChanged(true);

    if (!m_pendingCommand.isEmpty()) {
        const QString cmd = m_pendingCommand;
        const QJsonObject extra = m_pendingExtra;
        m_pendingCommand.clear();
        m_pendingExtra = QJsonObject();
        sendCommand(cmd, extra);
    }
}

void EngineBridge::onDisconnected()
{
    m_connected = false;
    m_buffer.clear();
    emit connectionChanged(false);
    if (!m_reconnectTimer->isActive()) {
        m_reconnectTimer->start();
    }
}

void EngineBridge::onReadyRead()
{
    QIODevice *io = device();
    if (!io) {
        return;
    }

    m_buffer += io->readAll();
    while (m_buffer.contains('\n')) {
        const int pos = m_buffer.indexOf('\n');
        const QByteArray line = m_buffer.left(pos).trimmed();
        m_buffer.remove(0, pos + 1);
        if (line.isEmpty()) {
            continue;
        }

        QJsonParseError err;
        const QJsonDocument doc = QJsonDocument::fromJson(line, &err);
        if (err.error != QJsonParseError::NoError || !doc.isObject()) {
            continue;
        }
        handleMessage(doc.object());
    }
}

void EngineBridge::handleMessage(const QJsonObject &obj)
{
    const QString type = obj.value(QStringLiteral("type")).toString();
    const QJsonObject payload = obj.value(QStringLiteral("payload")).toObject();

    if (type == QStringLiteral("system_status")) {
        emit systemStatusReceived(payload);
    } else if (type == QStringLiteral("action_status")) {
        emit actionStatusReceived(payload);
    } else if (type == QStringLiteral("training_progress")) {
        emit trainingProgressReceived(payload);
    } else if (type == QStringLiteral("training_state")) {
        emit trainingStateReceived(payload);
    } else if (type == QStringLiteral("scoring")) {
        emit scoringReceived(payload);
    } else if (type == QStringLiteral("training_plan")) {
        emit trainingPlanReceived(payload);
    } else if (type == QStringLiteral("assessment_plan")) {
        emit assessmentPlanReceived(payload);
    } else if (type == QStringLiteral("assessment_phase")) {
        emit assessmentPhaseReceived(payload);
    } else if (type == QStringLiteral("session_summary")) {
        emit sessionSummaryReceived(
            payload.value(QStringLiteral("summary_text")).toString());
    } else if (type == QStringLiteral("correction")) {
        emit correctionReceived(payload);
    } else if (type == QStringLiteral("encouragement")) {
        emit encouragementReceived(
            payload.value(QStringLiteral("text")).toString());
    } else if (type == QStringLiteral("skeleton_3d")) {
        emit skeleton3dReceived(payload);
    } else if (type == QStringLiteral("joint_angles")) {
        emit jointAnglesReceived(payload);
    } else if (type == QStringLiteral("vision_preview")) {
        emit visionPreviewReceived(payload);
    }
}
