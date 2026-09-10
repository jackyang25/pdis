// Optional browser regression check: set PLAYWRIGHT_MODULE to an installed playwright-core module.
// Start the web server first; DOCS_BASE_URL defaults to http://localhost:3102.
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ?? 'playwright-core');
const baseURL = process.env.DOCS_BASE_URL ?? 'http://localhost:3102';
import assert from 'node:assert/strict';
const browser = await chromium.launch({headless:true});
const page = await browser.newPage({viewport:{width:1440,height:900}, reducedMotion:'reduce'});
const errors=[]; page.on('pageerror', e=>errors.push(e.message));
await page.route('**/api/**', route=>route.fulfill({json:{}}));
try {
 await page.goto(`${baseURL}/docs`,{waitUntil:'networkidle'});
 const nav=page.getByRole('navigation',{name:'Documentation sections'});
 await nav.getByRole('link',{name:'Architecture',exact:true}).click();
 await page.waitForTimeout(400);
 assert.equal(await nav.getByRole('link',{name:'Architecture',exact:true}).getAttribute('aria-current'),'location');
 await nav.getByRole('link',{name:'Pipelines',exact:true}).click();
 await page.getByRole('button',{name:'Read stages',exact:true}).click();
 const tools=page.getByRole('group',{name:'Tool architecture'});
 await tools.getByRole('button',{name:'Scout',exact:true}).click();
 const stage=page.locator('summary').filter({hasText:'Parsed document'});
 await stage.click();
 assert.ok(await stage.locator('..').getByText('Consumes',{exact:true}).isVisible());
 await page.screenshot({path:'/tmp/pdis-docs-stages.png'});
 await page.getByRole('button',{name:'View diagram',exact:true}).click();
 assert.ok(await page.getByRole('button',{name:'Zoom in',exact:true}).isVisible());
 await page.screenshot({path:'/tmp/pdis-docs-diagram.png'});
 await nav.getByRole('link',{name:'Model instructions',exact:true}).click();
 assert.ok(await page.locator('#prompts').isVisible());
 const labels=page.locator('summary').filter({hasText:'What its labels mean'});
 await labels.focus();
 await page.keyboard.press('Enter');
 assert.equal(await labels.locator('..').getAttribute('open'),'');
 await nav.getByRole('link',{name:'Assistant context',exact:true}).click();
 await page.getByRole('heading',{name:'Draft the grantee ask',exact:true}).waitFor();
 await page.goto(`${baseURL}/docs`,{waitUntil:'networkidle'});
 await page.screenshot({path:'/tmp/pdis-docs-top.png'});
 await page.locator('html').evaluate(element=>element.classList.add('dark'));
 await page.screenshot({path:'/tmp/pdis-docs-dark.png'});
 await page.locator('html').evaluate(element=>element.classList.remove('dark'));
 for(const width of [390,320]) {
  await page.setViewportSize({width,height:800});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.locator('summary').filter({hasText:'On this page'}).click();
  await page.getByRole('link',{name:'FAQ',exact:true}).last().click();
  await page.locator('#faq summary').first().focus();
  await page.keyboard.press('Enter');
  assert.equal(await page.locator('#faq details').first().getAttribute('open'),'');
  await page.screenshot({path:`/tmp/pdis-docs-${width}.png`});
  await page.goto(`${baseURL}/docs`,{waitUntil:'networkidle'});
 }
 assert.deepEqual(errors,[]);
 console.log('PASS: navigation, stages/diagram, skill titles, mobile reflow and keyboard FAQ');
} finally {await browser.close();}
