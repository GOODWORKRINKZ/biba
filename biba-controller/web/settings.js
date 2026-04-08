const PID_FIELDS = [
  'yaw_rate_kp',
  'yaw_rate_ki',
  'yaw_rate_kd',
  'yaw_rate_deadband_dps',
  'yaw_rate_filter_hz',
  'stabilization_min_throttle',
  'neutral_stabilization_steering_limit',
  'neutral_stabilization_max_throttle',
];

const state = {
  payload: null,
};

const api = window.BIBA_SETTINGS_API || {
  settings: '/api/settings',
  pidTuning: '/api/settings/pid-tuning',
  motorTrim: '/api/settings/motor-trim',
  motorTest: '/api/settings/motor-test',
};

const TEXT = {
  unknown: 'неизвестно',
  notAvailable: 'н/д',
  armed: 'взведена',
  disarmed: 'разоружена',
  active: 'активен',
  inactive: 'не активен',
};

function formatError(message) {
  return `Ошибка: ${message}`;
}

function formatHttpStatus(status) {
  return `Код HTTP ${status}`;
}

function setValueIfIdle(id, value) {
  const node = document.getElementById(id);
  if (!node) {
    return;
  }
  if (document.activeElement !== node) {
    node.value = value;
  }
}

function numberPayload(fieldIds) {
  return Object.fromEntries(fieldIds.map((field) => [field, Number(document.getElementById(field).value)]));
}

function renderPlatform(payload) {
  const armed = payload.platform?.armed ? TEXT.armed : TEXT.disarmed;
  document.getElementById('platform-armed').textContent = armed;
  document.getElementById('platform-trim-mode').textContent = payload.platform?.trim_mode_active ? TEXT.active : TEXT.inactive;
  document.getElementById('platform-pid-revision').textContent = payload.pid_tuning?.pending_revision ?? payload.pid_tuning?.applied_revision ?? TEXT.notAvailable;
  document.getElementById('platform-trim-revision').textContent = payload.motor_trim?.pending_revision ?? payload.motor_trim?.applied_revision ?? TEXT.notAvailable;
}

function renderPid(payload) {
  if (!payload.pid_tuning) {
    return;
  }
  const pid = payload.pid_tuning;
  const source = pid.pending || pid.current || pid.defaults || {};
  PID_FIELDS.forEach((field) => setValueIfIdle(field, source[field] ?? 0));
  document.getElementById('pid-apply').disabled = Boolean(pid.armed);
  const status = document.getElementById('pid-status');
  if (pid.armed) {
    status.textContent = 'Платформа должна быть разоружена, чтобы применить настройки';
  } else if (pid.pending_revision !== null) {
    status.textContent = `Ожидает применения версия PID ${pid.pending_revision}`;
  } else if (pid.last_error) {
    status.textContent = formatError(pid.last_error);
  } else {
    status.textContent = `Применена версия ${pid.applied_revision}`;
  }
}

function renderTrim(payload) {
  if (!payload.motor_trim) {
    return;
  }
  const trim = payload.motor_trim;
  setValueIfIdle('motor_trim_value', trim.pending ?? trim.current ?? 0);
  document.getElementById('motor-trim-live-value').textContent = trim.live_value === null ? TEXT.notAvailable : trim.live_value.toFixed(2);
  document.getElementById('trim-apply').disabled = Boolean(trim.armed);
  const status = document.getElementById('trim-status');
  if (trim.armed) {
    status.textContent = 'Платформа должна быть разоружена, чтобы сохранить трим';
  } else if (trim.trim_mode_active) {
    status.textContent = 'На передатчике сейчас активен режим трима';
  } else if (trim.pending_revision !== null) {
    status.textContent = `Ожидает применения версия трима ${trim.pending_revision}`;
  } else if (trim.last_error) {
    status.textContent = formatError(trim.last_error);
  } else {
    status.textContent = `Сохранённый трим ${Number(trim.current).toFixed(2)}`;
  }
}

function renderMotorTest(payload) {
  const status = document.getElementById('motor-test-status');
  document.getElementById('motor-test-run').disabled = Boolean(payload.motor_test?.active);
  status.textContent = payload.motor_test?.active ? 'Проверка звучания моторов уже идёт' : 'Готово';
}

function render(payload) {
  state.payload = payload;
  renderPlatform(payload);
  renderPid(payload);
  renderTrim(payload);
  renderMotorTest(payload);
}

async function refreshSettings() {
  const response = await fetch(api.settings);
  const payload = await response.json();
  render(payload);
  return payload;
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.error || formatHttpStatus(response.status));
  }
  return body;
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('load-defaults').addEventListener('click', () => {
    const defaults = state.payload?.pid_tuning?.defaults || {};
    PID_FIELDS.forEach((field) => {
      if (field in defaults) {
        document.getElementById(field).value = defaults[field];
      }
    });
    document.getElementById('pid-status').textContent = 'Значения по умолчанию загружены в форму';
  });

  document.getElementById('pid-tuning-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const status = document.getElementById('pid-status');
    status.textContent = 'Применяю настройки PID...';
    try {
      const payload = numberPayload(PID_FIELDS);
      const body = await postJson(api.pidTuning, payload);
      if (state.payload) {
        state.payload.pid_tuning = body;
      }
      renderPid({ pid_tuning: body });
    } catch (error) {
      status.textContent = formatError(error.message);
    }
  });

  document.getElementById('motor-trim-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const status = document.getElementById('trim-status');
    status.textContent = 'Сохраняю трим...';
    try {
      const body = await postJson(api.motorTrim, { trim: Number(document.getElementById('motor_trim_value').value) });
      if (state.payload) {
        state.payload.motor_trim = body;
      }
      renderTrim({ motor_trim: body });
    } catch (error) {
      status.textContent = formatError(error.message);
    }
  });

  document.getElementById('motor-test-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const status = document.getElementById('motor-test-status');
    status.textContent = 'Запускаю проверку звучания моторов...';
    try {
      await postJson(api.motorTest, {
        pwm_mode: document.getElementById('test_pwm_mode').value,
        left_frequency_hz: Number(document.getElementById('test_left_frequency_hz').value),
        left_duty_percent: Number(document.getElementById('test_left_duty_percent').value),
        right_frequency_hz: Number(document.getElementById('test_right_frequency_hz').value),
        right_duty_percent: Number(document.getElementById('test_right_duty_percent').value),
        duration_ms: Number(document.getElementById('test_duration_ms').value),
      });
      status.textContent = 'Команда на проверку моторов отправлена';
    } catch (error) {
      status.textContent = formatError(error.message);
    }
  });

  refreshSettings().catch((error) => {
    document.getElementById('pid-status').textContent = formatError(error.message);
  });
  setInterval(() => {
    refreshSettings().catch(() => {});
  }, 1000);
});