#ifndef ENGINEBRIDGE_H
#define ENGINEBRIDGE_H

#include <QObject>
#include <QJsonObject>
#include <QByteArray>
#include <QTimer>

#include <QIODevice>

class QLocalSocket;
class QTcpSocket;

/**
 * 与 rehab-coach-rknn 核心引擎通信（JSON 行协议）。
 * Linux: Unix Socket /tmp/rehab_engine.sock
 * 其它平台: TCP 127.0.0.1:9002
 */
class EngineBridge : public QObject
{
    Q_OBJECT
public:
    explicit EngineBridge(QObject *parent = nullptr);
    ~EngineBridge() override;

    void connectEngine();
    bool isConnected() const;
    void sendCommand(const QString &command, const QJsonObject &extra = QJsonObject());

signals:
    void connectionChanged(bool connected);
    void systemStatusReceived(const QJsonObject &payload);
    void actionStatusReceived(const QJsonObject &payload);
    void trainingProgressReceived(const QJsonObject &payload);
    void trainingStateReceived(const QJsonObject &payload);
    void scoringReceived(const QJsonObject &payload);
    void trainingPlanReceived(const QJsonObject &payload);
    void assessmentPlanReceived(const QJsonObject &payload);
    void assessmentPhaseReceived(const QJsonObject &payload);
    void sessionSummaryReceived(const QString &text);
    void correctionReceived(const QJsonObject &payload);
    void encouragementReceived(const QString &text);
    void skeleton3dReceived(const QJsonObject &payload);
    void jointAnglesReceived(const QJsonObject &payload);
    void visionPreviewReceived(const QJsonObject &payload);

private slots:
    void onConnected();
    void onDisconnected();
    void onReadyRead();
    void tryConnect();

private:
    void setupSocket();
    QIODevice *device() const;
    bool isSocketConnected() const;
    void handleMessage(const QJsonObject &obj);
    void writeLine(const QJsonObject &obj);

    QLocalSocket *m_localSocket = nullptr;
    QTcpSocket *m_tcpSocket = nullptr;
    QTimer *m_reconnectTimer = nullptr;
    QByteArray m_buffer;
    bool m_useLocalSocket = false;
    bool m_connected = false;
    QString m_pendingCommand;
    QJsonObject m_pendingExtra;
};

#endif // ENGINEBRIDGE_H
