#ifndef FUSIONBRIDGE_H
#define FUSIONBRIDGE_H

#include <QObject>
#include <QSharedMemory>
#include <QTimer>
#include <QVector3D>

struct FusionFrame {
    QVector<QVector3D> joints;     // 融合后的3D关节
    QVector<double> imuMicroMotion; // IMU微动数据
    qint64 timestamp;
    int frameIndex;
};

class FusionBridge : public QObject
{
    Q_OBJECT
public:
    explicit FusionBridge(QObject *parent = nullptr);
    void startListening();
    void stopListening();

signals:
    void fusionFrameReady(const FusionFrame &frame);

private slots:
    void pollFrame();

private:
    QSharedMemory m_shm;
    QTimer *m_pollTimer;
    int m_lastFrameIndex = -1;
};
#endif // FUSIONBRIDGE_H
