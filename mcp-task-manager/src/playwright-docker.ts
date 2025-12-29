/**
 * Playwright Docker Integration for MCP Task Manager
 *
 * This module provides tools for running Playwright browser automation
 * inside Docker containers, eliminating port forwarding issues.
 */

import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

interface PlaywrightResult {
  success: boolean;
  data?: any;
  error?: string;
  stdout?: string;
  stderr?: string;
}

/**
 * Execute a Playwright script inside the Docker container
 */
async function executePlaywrightScript(
  containerName: string,
  script: string
): Promise<PlaywrightResult> {
  try {
    // Escape the script for shell execution
    const escapedScript = script.replace(/'/g, "'\\''");

    // Create a temporary file with the script and execute it
    const command = `docker exec ${containerName} bash -c "cat > /tmp/playwright-script.js << 'PLAYWRIGHT_EOF'
${script}
PLAYWRIGHT_EOF
node /tmp/playwright-script.js"`;

    const { stdout, stderr } = await execAsync(command, {
      maxBuffer: 10 * 1024 * 1024, // 10MB buffer for large outputs
    });

    // Try to parse JSON output if possible
    try {
      const result = JSON.parse(stdout.trim());
      return { success: true, data: result, stdout, stderr };
    } catch {
      // If not JSON, return raw output
      return { success: true, data: stdout.trim(), stdout, stderr };
    }
  } catch (error: any) {
    console.error('[playwright-docker] Script execution failed:', error.message);
    return {
      success: false,
      error: error.message,
      stdout: error.stdout,
      stderr: error.stderr,
    };
  }
}

/**
 * MCP Tools for Playwright Docker Integration
 */
export const playwrightDockerTools = [
  {
    name: 'playwright_init_docker',
    description: 'Initialize Playwright browser inside Docker container',
    inputSchema: {
      type: 'object',
      properties: {},
    },
    handler: async () => {
      const containerName = process.env.DOCKER_CONTAINER_NAME || 'yokeflow-container';

      const script = `
const { chromium } = require('playwright');
(async () => {
  try {
    // Test that Playwright is available
    const browser = await chromium.launch({
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    await browser.close();
    console.log(JSON.stringify({ success: true, message: 'Playwright initialized successfully' }));
  } catch (error) {
    console.log(JSON.stringify({ success: false, error: error.message }));
  }
})();
`;

      return await executePlaywrightScript(containerName, script);
    },
  },

  {
    name: 'playwright_test_docker',
    description: 'Run a browser test using Playwright inside Docker container',
    inputSchema: {
      type: 'object',
      properties: {
        url: {
          type: 'string',
          description: 'URL to navigate to (use localhost for container services)',
        },
        screenshotPath: {
          type: 'string',
          description: 'Path to save screenshot (relative to /workspace)',
        },
        actions: {
          type: 'array',
          description: 'Array of actions to perform (click, type, etc.)',
          items: {
            type: 'object',
            properties: {
              type: { type: 'string', enum: ['click', 'type', 'wait', 'screenshot'] },
              selector: { type: 'string' },
              value: { type: 'string' },
            },
          },
        },
      },
      required: ['url'],
    },
    handler: async (params: any) => {
      const containerName = process.env.DOCKER_CONTAINER_NAME || 'yokeflow-container';
      const { url, screenshotPath = '/workspace/screenshot.png', actions = [] } = params;

      // Build action script
      let actionScript = '';
      for (const action of actions) {
        switch (action.type) {
          case 'click':
            actionScript += `    await page.click('${action.selector}');\n`;
            actionScript += `    console.error('[Action] Clicked: ${action.selector}');\n`;
            break;
          case 'type':
            actionScript += `    await page.type('${action.selector}', '${action.value}');\n`;
            actionScript += `    console.error('[Action] Typed into ${action.selector}');\n`;
            break;
          case 'wait':
            actionScript += `    await page.waitForTimeout(${action.value || 1000});\n`;
            break;
          case 'screenshot':
            actionScript += `    await page.screenshot({ path: '${action.value || '/workspace/action-screenshot.png'}' });\n`;
            actionScript += `    console.error('[Action] Screenshot saved: ${action.value}');\n`;
            break;
        }
      }

      const script = `
const { chromium } = require('playwright');

(async () => {
  let browser;
  try {
    browser = await chromium.launch({
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const context = await browser.newContext();
    const page = await context.newPage();

    // Collect console messages
    const consoleMessages = [];
    const errors = [];

    page.on('console', msg => {
      const entry = { type: msg.type(), text: msg.text() };
      consoleMessages.push(entry);
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    // Navigate to URL
    await page.goto('${url}', { waitUntil: 'networkidle' });

    // Get page info
    const title = await page.title();
    const currentUrl = page.url();

    // Perform custom actions
${actionScript}

    // Take screenshot
    await page.screenshot({ path: '${screenshotPath}' });

    // Get page content info
    const bodyText = await page.evaluate(() => document.body.innerText);
    const hasContent = bodyText && bodyText.trim().length > 0;

    // Close browser
    await browser.close();

    // Return results
    console.log(JSON.stringify({
      success: true,
      url: currentUrl,
      title: title,
      screenshot: '${screenshotPath}',
      hasContent: hasContent,
      consoleMessages: consoleMessages,
      errors: errors,
      errorCount: errors.length
    }, null, 2));

  } catch (error) {
    if (browser) await browser.close();
    console.log(JSON.stringify({
      success: false,
      error: error.message,
      stack: error.stack
    }));
    process.exit(1);
  }
})();
`;

      return await executePlaywrightScript(containerName, script);
    },
  },

  {
    name: 'playwright_verify_docker',
    description: 'Comprehensive verification of a web page using Playwright inside Docker',
    inputSchema: {
      type: 'object',
      properties: {
        url: {
          type: 'string',
          description: 'URL to verify',
        },
        taskId: {
          type: 'string',
          description: 'Task ID for screenshot naming',
        },
        checks: {
          type: 'array',
          description: 'Array of checks to perform',
          items: {
            type: 'object',
            properties: {
              type: { type: 'string', enum: ['text', 'element', 'api'] },
              selector: { type: 'string' },
              expected: { type: 'string' },
            },
          },
        },
      },
      required: ['url', 'taskId'],
    },
    handler: async (params: any) => {
      const containerName = process.env.DOCKER_CONTAINER_NAME || 'yokeflow-container';
      const { url, taskId, checks = [] } = params;
      const screenshotPath = `/workspace/screenshots/task_${taskId}_verification.png`;

      // Build checks script
      let checksScript = '';
      for (const check of checks) {
        switch (check.type) {
          case 'text':
            checksScript += `
    // Check for text: ${check.expected}
    const hasText = await page.evaluate((text) => {
      return document.body.innerText.includes(text);
    }, '${check.expected}');
    checkResults.push({ type: 'text', expected: '${check.expected}', found: hasText });
`;
            break;
          case 'element':
            checksScript += `
    // Check for element: ${check.selector}
    const element = await page.$(\'${check.selector}\');
    checkResults.push({ type: 'element', selector: '${check.selector}', found: !!element });
`;
            break;
          case 'api':
            checksScript += `
    // Check API endpoint: ${check.expected}
    const apiResponse = await page.evaluate(async (endpoint) => {
      try {
        const response = await fetch(endpoint);
        return { ok: response.ok, status: response.status };
      } catch (error) {
        return { ok: false, error: error.message };
      }
    }, '${check.expected}');
    checkResults.push({ type: 'api', endpoint: '${check.expected}', result: apiResponse });
`;
            break;
        }
      }

      const script = `
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  let browser;
  try {
    // Ensure screenshots directory exists
    const screenshotDir = path.dirname('${screenshotPath}');
    if (!fs.existsSync(screenshotDir)) {
      fs.mkdirSync(screenshotDir, { recursive: true });
    }

    browser = await chromium.launch({
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const context = await browser.newContext();
    const page = await context.newPage();

    // Collect console messages and network errors
    const consoleMessages = [];
    const networkErrors = [];
    const jsErrors = [];

    page.on('console', msg => {
      const entry = { type: msg.type(), text: msg.text() };
      consoleMessages.push(entry);
      if (msg.type() === 'error') {
        jsErrors.push(msg.text());
      }
    });

    page.on('pageerror', error => {
      jsErrors.push(error.message);
    });

    page.on('requestfailed', request => {
      networkErrors.push({
        url: request.url(),
        failure: request.failure()
      });
    });

    // Navigate to URL
    console.error('[Navigation] Navigating to ${url}...');
    const response = await page.goto('${url}', {
      waitUntil: 'networkidle',
      timeout: 30000
    });

    // Check response status
    const status = response ? response.status() : 0;
    const ok = response ? response.ok() : false;

    // Get page info
    const title = await page.title();
    const currentUrl = page.url();

    // Perform custom checks
    const checkResults = [];
${checksScript}

    // Take screenshot
    await page.screenshot({ path: '${screenshotPath}', fullPage: false });
    console.error('[Screenshot] Saved to ${screenshotPath}');

    // Check for common issues
    const hasContent = await page.evaluate(() => {
      return document.body && document.body.innerText.trim().length > 0;
    });

    // Close browser
    await browser.close();

    // Determine overall success
    const hasJsErrors = jsErrors.length > 0;
    const hasNetworkErrors = networkErrors.length > 0;
    const allChecksPassed = checkResults.every(r => r.found || (r.result && r.result.ok));
    const overallSuccess = ok && !hasJsErrors && !hasNetworkErrors && hasContent;

    // Return comprehensive results
    console.log(JSON.stringify({
      success: overallSuccess,
      taskId: '${taskId}',
      url: currentUrl,
      title: title,
      status: status,
      screenshot: '${screenshotPath}',
      hasContent: hasContent,
      checks: checkResults,
      allChecksPassed: allChecksPassed,
      consoleMessageCount: consoleMessages.length,
      jsErrors: jsErrors,
      networkErrors: networkErrors,
      summary: {
        jsErrorCount: jsErrors.length,
        networkErrorCount: networkErrors.length,
        checksRun: checkResults.length,
        checksPassed: checkResults.filter(r => r.found || (r.result && r.result.ok)).length
      }
    }, null, 2));

  } catch (error) {
    if (browser) await browser.close();
    console.log(JSON.stringify({
      success: false,
      taskId: '${taskId}',
      error: error.message,
      stack: error.stack
    }));
    process.exit(1);
  }
})();
`;

      return await executePlaywrightScript(containerName, script);
    },
  },
];

// Export individual functions for direct use
export { executePlaywrightScript };