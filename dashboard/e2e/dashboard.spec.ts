import {test,expect} from '@playwright/test';
test('actual research overview and measured replay chart',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');
 await expect(page.getByRole('heading',{name:'Research, with evidence.'})).toBeVisible();
 await expect(page.getByText('$98,882.77')).toBeVisible();
 await expect(page.locator('.recharts-line-curve').first()).toBeVisible();
 await expect(page.getByText('No strategy is approved for live trading.')).toBeVisible();
 await page.screenshot({path:'../docs/dashboard-overview.png',fullPage:true});
 expect(errors).toEqual([]);
});
test('real rejected trials, backtest and model manifest inspection',async({page})=>{
 await page.goto('/discovery');
 await page.getByRole('button',{name:'Bounded ES Optuna trials'}).click();
 await expect(page.getByText('Full artifact · configuration, metrics and limitations')).toBeVisible();
 await page.getByRole('link',{name:'Backtests',exact:true}).click();
 await page.getByRole('button',{name:'Equal-weight portfolio versus SPY'}).click();
 await expect(page.locator('.recharts-line-curve').first()).toBeVisible();
 await page.getByRole('link',{name:'Machine learning',exact:true}).click();
 await page.getByRole('button',{name:'Experimental quote-event ridge model'}).click();
 await expect(page.getByText('UNVALIDATED',{exact:true}).first()).toBeVisible();
});
test('paper controls confirm and reject unauthorized mutation',async({page})=>{
 await page.goto('/paper');
 await page.getByRole('button',{name:'ES experimental replay and restart'}).click();
 await page.getByRole('textbox',{name:'Operator reason'}).fill('browser permission test');
 page.once('dialog',dialog=>dialog.accept());
 await page.getByRole('button',{name:'kill',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('Role does not authorize');
});
test('SSE notices and invalid bearer errors',async({page})=>{
 await page.goto('/system');
 await expect(page.getByText('LIMITED',{exact:true})).toBeVisible();
 const event=await page.evaluate(async()=>{const r=await fetch('/api/v1/events');const reader=r.body!.getReader();const first=await reader.read();await reader.cancel();return new TextDecoder().decode(first.value)});
 expect(event).toContain('event: refresh');
 await page.getByLabel('API access token').fill('invalid-token');
 await page.getByRole('button',{name:'Connect',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('Invalid access token');
});
test('mobile navigation remains keyboard accessible',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/');
 await page.getByRole('button',{name:'Toggle navigation'}).click();
 await page.getByRole('link',{name:'System health',exact:true}).click();
 await expect(page.getByRole('heading',{name:'System health',exact:true})).toBeVisible();
});

test('bounded agent displays actual sessions and rejects unauthorized controls',async({page})=>{
 await page.goto('/agent');
 await expect(page.getByRole('heading',{name:'Bounded research agent',exact:true})).toBeVisible();
 await expect(page.getByText('Current demonstration uses a scripted planner',{exact:false})).toBeVisible();
 await page.getByLabel('Research session').selectOption('54f1b7c8cab841f1a751c98f5d762c75');
 await expect(page.getByText('Actual hypotheses, iterations, usage and findings')).toBeVisible();
 await page.getByLabel('Research control reason').fill('browser authorization test');
 page.once('dialog',d=>d.accept());
 await page.getByRole('button',{name:'pause',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('Role does not authorize');
 await page.screenshot({path:'../docs/dashboard-agent.png',fullPage:true});
});
