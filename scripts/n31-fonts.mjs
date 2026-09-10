// Build-time only: self-host variable script subsets from Fontsource's OFL packages.
import { mkdir, writeFile } from 'node:fs/promises'
import { execFileSync } from 'node:child_process'
const families = ['vazirmatn', 'noto-sans-arabic', 'noto-sans-hebrew', 'noto-sans-devanagari', 'noto-sans-sc', 'noto-sans-jp', 'noto-sans-kr']
await mkdir('public/fonts/n31', { recursive: true })
let css = '/* Self-hosted variable fonts; unicode ranges fetch only glyph subsets in use. */\n'
for (const family of families) {
  const meta = await (await fetch(`https://registry.npmjs.org/@fontsource-variable/${family}/5.3.0`)).json()
  const archive = `public/fonts/n31/${family}.tgz`
  await writeFile(archive, Buffer.from(await (await fetch(meta.dist.tarball)).arrayBuffer()))
  const source = execFileSync('tar', ['-xOf', archive, 'package/wght.css'], { encoding: 'utf8' })
  const urls = [...new Set([...source.matchAll(/url\(\.\/files\/([^)]*)\)/g)].map(m => m[1]))]
  for (const file of urls) {
    await writeFile(`public/fonts/n31/${file}`, execFileSync('tar', ['-xOf', archive, `package/files/${file}`], { maxBuffer: 30_000_000 }))
  }
  await writeFile(`public/fonts/n31/${family}-LICENSE`, execFileSync('tar', ['-xOf', archive, 'package/LICENSE']))
  css += source.replaceAll('./files/', '/fonts/n31/') + '\n'
  const { unlink } = await import('node:fs/promises')
  await unlink(archive)
  console.log(family, meta.version, urls.length)
}
await writeFile('src/styles/fonts.css', css)
