// Local production-artifact startup probe; does not assume a Kimi hosting contract.
import { preview } from 'vite'
import { chromium } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
const browser = await chromium.launch()
const results = []
try {
  for (const mode of ['demo','server']) {
    const server = await preview({ build: { outDir:`dist/${mode}` }, preview: { host:'127.0.0.1', port:4400, strictPort:true } })
    try {
      for (const locale of ['fa','ar','he','zh-CN']) {
        const page = await browser.newPage()
        const errors = []
        page.on('pageerror', e => errors.push(e.message))
        page.on('response', r => { if (!r.ok() && !r.url().includes('/api/')) errors.push(`${r.status()} ${r.url()}`) })
        await page.addInitScript(locale => {
          localStorage.setItem('cve-locale', locale)
          localStorage.setItem('cve-demo-state-v1', '{broken json')
        }, locale)
        await page.goto('http://127.0.0.1:4400')
        await page.locator(mode === 'demo' ? '.content .wrap' : '.login-card').waitFor()
        await page.evaluate(() => document.fonts.ready)
        if (errors.length) throw new Error(JSON.stringify({ mode, locale, errors }))
        results.push({ mode, locale, status:'PASS', errors })
        await page.close()
      }
    } finally { await new Promise(resolve => server.httpServer.close(resolve)) }
  }
} finally { await browser.close() }
await mkdir('report', { recursive:true })
await writeFile('report/n31-preview.json', JSON.stringify(results,null,2)+'\n')
console.log(`${results.length} production startup probes passed`)
