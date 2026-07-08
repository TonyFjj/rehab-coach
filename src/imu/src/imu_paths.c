#include "imu_paths.h"

#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <libgen.h>
#include <sys/stat.h>

static char g_data_dir[PATH_MAX];
static char g_assessment_log[PATH_MAX];
static int g_ready = 0;

static void init_paths(void)
{
    if (g_ready) {
        return;
    }

    const char *env = getenv("IMU_DATA_DIR");
    if (env != NULL && env[0] != '\0') {
        snprintf(g_data_dir, sizeof(g_data_dir), "%s", env);
    } else {
        char exe[PATH_MAX];
        ssize_t n = readlink("/proc/self/exe", exe, sizeof(exe) - 1);
        if (n > 0) {
            char exe_copy[PATH_MAX];
            exe[n] = '\0';
            strncpy(exe_copy, exe, sizeof(exe_copy) - 1);
            exe_copy[sizeof(exe_copy) - 1] = '\0';

            char *build_dir = dirname(exe_copy);
            char candidate[PATH_MAX];
            snprintf(candidate, sizeof(candidate), "%s/../data", build_dir);

            char resolved[PATH_MAX];
            if (realpath(candidate, resolved) != NULL) {
                strncpy(g_data_dir, resolved, sizeof(g_data_dir) - 1);
            } else {
                snprintf(g_data_dir, sizeof(g_data_dir), "%s", candidate);
            }
        } else {
            strncpy(g_data_dir, "./data", sizeof(g_data_dir) - 1);
        }
    }

    g_data_dir[sizeof(g_data_dir) - 1] = '\0';
    snprintf(
        g_assessment_log,
        sizeof(g_assessment_log),
        "%s/assessment_log.csv",
        g_data_dir
    );
    g_assessment_log[sizeof(g_assessment_log) - 1] = '\0';
    g_ready = 1;
}

const char *imu_get_data_dir(void)
{
    init_paths();
    return g_data_dir;
}

const char *imu_get_assessment_log_path(void)
{
    init_paths();
    return g_assessment_log;
}

void imu_ensure_data_dir(void)
{
    init_paths();
    mkdir(g_data_dir, 0755);
}
