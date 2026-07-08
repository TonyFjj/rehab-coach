#ifndef VISIONBRIDGE_H
#define VISIONBRIDGE_H

#include <QObject>
#include <QLocalSocket>
#include <QTimer>
#include <QVector3D>
#include <QJsonObject>

struct Skeleton3D {
    QVector<QVector3D> joints;  // 17个3D关节点
    qint64 timestamp;
};

class VisionBridge : public QObject
{
    Q_OBJECT
public:
    explicit VisionBridge(QObject *parent = nullptr);
    void startCapture();
    void stopCapture();

signals:
    void skeletonReady(const Skeleton3D &skel);
    void connectionChanged(bool connected);

private slots:
    void onReadyRead();
    void onConnected();
    void onDisconnected();

private:
    QLocalSocket *m_socket;
    QTimer *m_reconnectTimer;
    void tryConnect();
};
#endif // VISIONBRIDGE_H
