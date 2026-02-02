from .profiler import (
    profiler,
    profile,
    profile_loop,
    OperationCategory,
    ProfileContext,
    AgentProfiler,
    enable_profiling,
    disable_profiling,
    is_profiling_enabled,
    set_auto_save_interval,
    print_profile_report,
    save_profile_report,
    get_profiler,
    get_profiler_config,
    log_events,  # backward compatibility
)
