import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';

const DEFAULT_APP_EXE =
  'C:\\Users\\Korobka\\AppData\\Local\\Programs\\DeepSeek Harness\\DeepSeek Harness.exe';
const DEFAULT_CLI_JS =
  'C:\\Users\\Korobka\\AppData\\Local\\Programs\\DeepSeek Harness\\resources\\app.asar\\dsh\\node_modules\\@deepseek-ai\\dsh-desktop-host\\lib\\cli.js';
const DEFAULT_DSH_CMD =
  'C:\\Users\\Korobka\\AppData\\Local\\Programs\\DeepSeek Harness\\resources\\runtime\\cli\\bin\\dsh.cmd';

/**
 * The agent is launched through the Electron binary in Node mode and the Desktop
 * CLI entry point. Going through the .cmd shim breaks multi-line prompts, so the
 * executable is spawned directly whenever it is available.
 */
export function describeLauncher() {
  const appExe = (process.env.DSH_APP_EXE ?? '').trim() || DEFAULT_APP_EXE;
  const cliJs = (process.env.DSH_CLI_JS ?? '').trim() || DEFAULT_CLI_JS;
  return existsSync(appExe) && existsSync(cliJs)
    ? appExe
    : (process.env.DSH_CLI ?? '').trim() || DEFAULT_DSH_CMD;
}

/** The DSH agent only exists where the Desktop app is installed (the local PC). */
export function agentAvailable() {
  const appExe = (process.env.DSH_APP_EXE ?? '').trim() || DEFAULT_APP_EXE;
  const cliJs = (process.env.DSH_CLI_JS ?? '').trim() || DEFAULT_CLI_JS;
  const cli = (process.env.DSH_CLI ?? '').trim();

  // The Electron app path alone is not enough: the headless CLI entry point
  // must exist too. A custom launcher is accepted as an alternative.
  return (existsSync(appExe) && existsSync(cliJs)) || Boolean(cli && existsSync(cli));
}

function buildCommand(prompt) {
  const appExe = (process.env.DSH_APP_EXE ?? '').trim() || DEFAULT_APP_EXE;
  const cliJs = (process.env.DSH_CLI_JS ?? '').trim() || DEFAULT_CLI_JS;
  if (existsSync(appExe) && existsSync(cliJs)) {
    return {
      file: appExe,
      args: ['--expose-internals', cliJs, 'headless', prompt],
      env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' },
    };
  }
  // Fallback for non-standard installations that only ship the launcher script.
  const cli = (process.env.DSH_CLI ?? '').trim() || DEFAULT_DSH_CMD;
  return { file: 'cmd.exe', args: ['/d', '/s', '/c', cli, 'headless', prompt], env: process.env };
}

/**
 * Run one headless agent turn and return its answer.
 * The agent inherits the process environment (DEEPSEEK_API_KEY included).
 */
export function askAgent({ prompt, workspace, timeoutMs = 180_000 }) {
  return new Promise((resolve, reject) => {
    const command = buildCommand(prompt);
    const child = spawn(command.file, command.args, {
      cwd: workspace,
      windowsHide: true,
      env: command.env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    let stdout = '';
    let stderr = '';
    let settled = false;

    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      child.kill();
      reject(new Error(`Агент не ответил за ${Math.round(timeoutMs / 1000)} с.`));
    }, timeoutMs);

    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    child.stdout.on('data', (chunk) => {
      stdout += chunk;
    });
    child.stderr.on('data', (chunk) => {
      stderr += chunk;
    });

    child.on('error', (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(
        error.code === 'ENOENT'
          ? new Error(`Не найден исполняемый файл агента: ${command.file}. Задай DSH_APP_EXE.`)
          : error,
      );
    });

    child.on('close', (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      const answer = cleanAnswer(stdout);
      if (answer) return resolve({ text: answer, code, stderr });
      if (code !== 0) {
        const detail = summarize(stderr) || summarize(stdout);
        return reject(new Error(`CLI вернул код ${code}${detail ? `: ${detail}` : ''}`));
      }
      resolve({ text: '(пустой ответ)', code, stderr });
    });
  });
}

/** Drop progress noise the CLI writes around the answer. */
function cleanAnswer(stdout) {
  return String(stdout)
    .replace(/\u001b\[[0-9;]*m/g, '')
    .split(/\r?\n/)
    .filter((line) => !/^\[llm-deepseek-api-key\]/.test(line.trim()))
    .join('\n')
    .trim();
}

function summarize(text) {
  return String(text)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !/^\[llm-deepseek-api-key\]/.test(line))
    .slice(-3)
    .join(' ')
    .slice(0, 300);
}
