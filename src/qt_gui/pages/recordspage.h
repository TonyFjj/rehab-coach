#ifndef RECORDSPAGE_H
#define RECORDSPAGE_H

#include <QCheckBox>
#include <QDateTime>
#include <QGridLayout>
#include <QLabel>
#include <QList>
#include <QProgressBar>
#include <QPushButton>
#include <QScrollArea>
#include <QString>
#include <QStringList>
#include <QStackedWidget>
#include <QVBoxLayout>
#include <QWidget>
#include "../models/scoreengine.h"

struct TrainRecord {
    int index = 0;                 // 第几次训练
    QString actionName;            // 训练动作
    int compositeScore = 0;        // 综合得分
    int completion = 0;            // 完成度
    QString level;                 // 康复级别
    QDateTime timestamp;           // 训练完成时间
    QStringList blockNames;       // L1/L2/L3/L4 综合训练中的四个功能块名称
    QList<int> blockScores;       // 四个功能块对应得分
    QString advice;                // 训练建议
    QString source = QStringLiteral("training_integrated"); // 数据来源，训练记录只保存一体化训练
};

class RecordsPage : public QWidget
{
    Q_OBJECT
public:
    explicit RecordsPage(QWidget *parent = nullptr);
    void refresh();
    void applyFontScale();
    // 训练记录只接收“训练”页面产生的数据，不接收评估页面数据。
    void appendTrainingRecord(const QString &actionName, const ScoreResult &result, int completion = -1);
    int lastCompositeScore() const;
    QString lastLevelName() const;
    QString lastLevelColor() const;
    QString lastAdvice() const;

private:
    void setupUI();
    void buildListPage();
    void buildDetailPage();
    void loadStoredData();
    void saveStoredData() const;
    void rebuildSummaryRecord();
    void showRecordDetail(int recordIndex);
    void clearScoreGrid();
    void addScoreRow(int row, const QString &name, int score, const QString &desc);
    void deleteSelectedRecords();

    QStackedWidget *m_stack = nullptr;
    QWidget *m_listPage = nullptr;
    QWidget *m_detailPage = nullptr;

    QLabel *m_title = nullptr;
    QLabel *m_summary = nullptr;
    QScrollArea *m_scrollArea = nullptr;
    QWidget *m_scoreContainer = nullptr;
    QVBoxLayout *m_scoreLayout = nullptr;

    QPushButton *m_backBtn = nullptr;
    QLabel *m_detailTitle = nullptr;
    QLabel *m_detailMeta = nullptr;
    QLabel *m_detailComposite = nullptr;
    QLabel *m_detailLevel = nullptr;
    QLabel *m_detailAdvice = nullptr;
    QLabel *m_detailScoreTitle = nullptr;
    QWidget *m_detailScoresPanel = nullptr;
    QScrollArea *m_detailScroll = nullptr;
    QGridLayout *m_detailScoresGrid = nullptr;

    QList<TrainRecord> m_records;
    QList<QCheckBox*> m_deleteChecks;
    bool m_recordsLoaded = false;
    int m_openDetailIndex = -1;
};

#endif // RECORDSPAGE_H
