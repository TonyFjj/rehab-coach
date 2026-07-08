#ifndef WIDGET_H
#define WIDGET_H

#include <QWidget>

class QLabel;
class QEvent;
class QResizeEvent;
class MainWindow;

QT_BEGIN_NAMESPACE
namespace Ui { class Widget; }
QT_END_NAMESPACE

class Widget : public QWidget
{
    Q_OBJECT

public:
    explicit Widget(QWidget *parent = nullptr);
    ~Widget();

public slots:
    void set_style();

protected:
    void resizeEvent(QResizeEvent *event) override;
    bool eventFilter(QObject *watched, QEvent *event) override;

private slots:
    void onLoginClicked();

private:
    void setupResponsiveLayout();
    void setupQuickStartPanel();
    void setupPictureLabel();
    void setupLogoLabel();
    void fitWindowToCurrentScreen();
    void setPicture(const QString &picturePath);
    void updatePicture();
    void updateLogo();
    void applyLoginStyle(int styleIndex);
    QString loginStylePath(int styleIndex) const;
    QString loginPicturePath(int styleIndex) const;

private:
    Ui::Widget *ui;
    QLabel *m_pictureLabel;
    QLabel *m_logoLabel;
    QString m_currentPicturePath;
    int m_currentStyleIndex;
    MainWindow *m_mainWindow;
};

#endif // WIDGET_H
