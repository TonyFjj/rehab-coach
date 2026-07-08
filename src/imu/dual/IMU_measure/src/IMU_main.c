/**
 * @file IMU_main.c
 * @brief 双IMU数据采集 + 双侧康复评估主程序
 *
 * 流程:
 *   1. 同时采集左手+右手IMU数据 (两个独立串口, 两个独立线程)
 *   2. 采集完成后, 自动调用双侧评估模块
 *   3. 输出六大维度康复评估报告 (含双侧对称性)
 */
#include "collect_data.h"
#include "data_analysis.h"

int main(int argc, char *argv[])
{
    char csv_left[CSV_PATH_MAX];
    char csv_right[CSV_PATH_MAX];

    /* ---- Step 1: 双IMU数据采集 (自动生成新文件名) ---- */
    if (collect_dual_data(argc, argv, csv_left, csv_right) != 0) {
        return 1;
    }

    /* ---- Step 2: 自动运行双侧康复评估 ---- */
    printf("\n[系统] 双IMU数据采集完成, 开始双侧康复评估分析...\n");
    printf("[系统] 左手文件: %s\n", csv_left);
    printf("[系统] 右手文件: %s\n", csv_right);
    run_dual_hand_assessment(csv_left, csv_right);

    return 0;
}
