#ifndef VISIONPREVIEWWIDGET_H
#define VISIONPREVIEWWIDGET_H

#include <QFrame>
#include <QLabel>
#include <QJsonObject>
#include <QPixmap>
#include <QRect>
#include <QString>
#include <QWidget>

class QMovie;
class QBuffer;
class QProgressBar;

class VisionPreviewWidget : public QFrame
{
    Q_OBJECT
public:
    explicit VisionPreviewWidget(QWidget *parent = nullptr);

    void setTopRightText(const QString &text);
    /** 画面左上角：训练中动作 / 次数 / 角度 */
    void setTopLeftText(const QString &text);
    /** 画面顶部半透明提示条（视觉质量 / 遮挡等） */
    void setTopBarText(const QString &text);
    void setBottomBarText(const QString &text);
    void setRightCameraGif(const QString &gifPath);
    void clearRightCameraGif();

    /** 画面顶部进度条（位于右上角状态文字左侧） */
    QProgressBar *topProgressBar() const { return m_topProgressBar; }
    QLabel *topCountdownLabel() const { return m_topCountdownLabel; }
    void setTopProgressVisible(bool visible);
    void setTopCountdownVisible(bool visible);
    void refreshOverlays();

public slots:
    void updatePreview(const QJsonObject &payload);
    void clearPreview();

protected:
    void resizeEvent(QResizeEvent *event) override;

private:
    void refreshScaledPixmap();
    void repositionOverlays();
    QRect previewImageRect() const;
    void updateGifOverlay();

    QWidget *m_viewport = nullptr;
    QLabel *m_imageLabel = nullptr;
    QLabel *m_gifOverlayLabel = nullptr;
    QMovie *m_gifMovie = nullptr;
    QBuffer *m_gifBuffer = nullptr;
    QLabel *m_topRightLabel = nullptr;
    QLabel *m_topLeftLabel = nullptr;
    QLabel *m_topBarLabel = nullptr;
    QLabel *m_bottomBarLabel = nullptr;
    QProgressBar *m_topProgressBar = nullptr;
    QLabel *m_topCountdownLabel = nullptr;
    QPixmap m_sourcePixmap;
    QString m_currentGifPath;
    QString m_lastBottomBarText;
};

#endif // VISIONPREVIEWWIDGET_H
