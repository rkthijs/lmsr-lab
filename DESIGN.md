# Design Conversation — Internal Prediction Market Platform

**Primary source of truth for this project.**

- **Original chat**: Exported from https://claude.ai/share/b4580732-4d55-4ba0-8177-063a5f6d0527
- **Date**: May 2025 (Bob + Claude)
- **Purpose**: Detailed mathematical and architectural design for building an internal-company prediction market / forecasting tool.
- **Key outcome**: Decision to build a clean, numerically stable LMSR-based market maker engine as the foundation (binary markets first, fixed `b`, play money, strong emphasis on calibration scoring and proper accounting).

This file is the living reference for what we are building. All major decisions (market mechanism, numerical methods, resolution rules, scoring, data model, etc.) should be traceable back to this conversation.

---

https://claude.ai/share/b4580732-4d55-4ba0-8177-063a5f6d0527


Open source prediction market projects
Shared by Bob
This is a copy of a chat between Claude and Bob. Content may include unverified or unsafe content that do not represent the views of Anthropic. Shared snapshot may contain attachments and data not displayed here.

what are the best open source projects for making a prediction market?

May 19

Searched the web
Searched the web
Here's a breakdown of the best open source options for building a prediction market, organized by use case:

Blockchain / Decentralized
Augur — The most established open-source decentralized prediction market protocol. It operates on Ethereum and supports binary, scalar, and multiple-choice markets, with REP tokens used for governance and dispute resolution. Good for developers who want full decentralization and a proven codebase. The repo is on GitHub at AugurProject/augur.

Gnosis Conditional Token Framework — Gnosis's Conditional Token Framework is a core innovation that allows for the tokenization of outcomes, enabling developers to create complex prediction markets and event-based financial products. It's more of a primitive/infrastructure layer than a full product, making it great for builders who want to compose their own system on top. The smart contracts repo (gnosis/conditional-tokens-contracts) has ~192 stars on GitHub.

kuestcom/prediction-market — A Polymarket-style Web3 decentralized prediction market you can launch in minutes. Good for quickly spinning up a Polymarket clone with minimal setup.

Traditional / Non-Crypto
SocialPredict (openpredictionmarkets/socialpredict) — An easy-to-deploy prediction market platform with a long-term roadmap covering service architecture (2025), microservices & math improvements (2026), cloud & UX (2027), and HPC/analytics (2028–2030). You can see it running at BrierFoxForecast. Best if you want a self-hosted, no-crypto platform.

PredictOS (PredictionXBT/PredictOS) — An all-in-one open-source framework for prediction markets. Newer but worth evaluating if you want a batteries-included approach.

Tooling / Trading Infrastructure
If you're not building the market itself but want to interact with or build on top of existing ones:

PMXT is essentially "CCXT for prediction markets" — a unified API for trading on Polymarket, Kalshi, and others, useful for market-making, data analysis, and arbitrage.
Awesome-Prediction-Market-Tools (aarora4 on GitHub) is a curated list covering AI agents, analytics, APIs, dashboards, copy trading, alerting, and more.
Quick Recommendation Guide
Goal	Best Pick
Self-hosted, no crypto	SocialPredict
Ethereum-native, full decentralization	Augur
Build custom markets on-chain	Gnosis CTF
Polymarket-style clone fast	kuestcom/prediction-market
Trade/integrate with existing markets	PMXT
What's your use case — are you leaning toward crypto/on-chain, or a traditional web app?

what is the advantange of crypto?

May 19
For prediction markets specifically, crypto offers a few meaningful advantages:

Settlement without a trusted middleman — Smart contracts automatically pay out when a market resolves. You don't need to trust the platform operator to actually send you the money.

Global access — Anyone with a crypto wallet can participate, regardless of country. Traditional prediction markets are heavily restricted by jurisdiction (Kalshi is US-only, PredictIt has limits, etc.).

Transparency — Every trade and market resolution is publicly verifiable on-chain. You can audit the entire history yourself.

Censorship resistance — No single company can shut down the market or freeze your funds. Augur famously lets anyone create a market on anything.

Composability — Outcome tokens from one protocol (like Gnosis CTF) can plug into other DeFi protocols — lending, liquidity pools, etc. This is unique to crypto and enables financial primitives that don't exist in traditional systems.

The tradeoffs are real though: gas fees, wallet UX friction, regulatory gray areas, and smart contract risk. For an internal company forecasting tool or a low-stakes community market, a simple self-hosted app like SocialPredict is probably easier and more practical. Crypto shines when you need trustless, permissionless, global participation.

ok, what would you use for an internal company tool?

May 19
For an internal company tool, I'd skip crypto entirely and go with SocialPredict or just build something lightweight yourself.

SocialPredict is probably the best off-the-shelf option — it's designed to be self-hosted, has a clean roadmap, and you can see it running in production at BrierFoxForecast. It handles the core mechanics (market creation, trading, resolution) without any blockchain complexity.

But honestly, for internal use, a custom build is very viable because your requirements are simpler than a public market:

No need for trustless settlement — you control resolution
No need for real money — play money or point systems work great
Small user base — no scaling concerns early on
You control auth — can just plug into your existing SSO/identity system
A typical lightweight stack would be something like a Next.js or React frontend + PostgreSQL + a simple Node/Python backend. The core math (a LMSR or CPMM automated market maker) is well-documented and not that hard to implement. Manifold Markets, which is one of the most popular internal forecasting tools, runs on exactly this kind of architecture.

The main questions that would shape the choice:

Do you want play money or real stakes?
How many users — a team of 20 vs. a company of 2,000 is a different problem
Do you want to self-host, or would a managed service like Metaculus or Manifold's hosted offering work?
What's the rough scale and context?

ok, what would be the parts of my own version if I were to spec it?

May 19
Here are the core components you'd need to spec out:

Data Model
The heart of everything. Key entities:

Markets — question, description, close date, resolution criteria, status (open/closed/resolved)
Users — balance, portfolio
Positions — who holds what shares in which outcome
Trades — full history of every transaction
Outcomes — the possible results (YES/NO for binary, or multiple choices)
Market Maker (the math engine)
This is the most technically interesting part. You need a mechanism that sets prices and accepts trades without requiring two users to match. The standard choices are:

LMSR (Logarithmic Market Scoring Rule) — classic, well-studied, used by academic and internal markets. Fixed subsidy model.
CPMM (Constant Product Market Maker) — what Manifold and Polymarket use. Simpler to implement, behaves like Uniswap.
For an internal tool, CPMM is probably the easier starting point.

Core Backend Services
Trade execution — validate a trade, update shares, update prices atomically
Balance management — credit/debit user accounts
Market resolution — admin closes a market and declares the outcome, winners get paid out
Leaderboard/scoring — tracking who's calibrated well over time
API Layer
REST or GraphQL endpoints for:

Create/list/get markets
Place trades
Get current prices and order book state
User portfolio and history
Admin: resolve market
Frontend
Market listing/discovery page
Individual market page with price chart + trade interface
User profile with portfolio and trade history
Admin panel for creating and resolving markets
Leaderboard
Auth & Identity
For internal use this is usually the easiest part — plug into whatever your company already uses (Google SSO, Okta, Active Directory via OAuth/SAML). No need to build auth from scratch.

Notifications (optional but high-value)
Market about to close
Market you hold a position in was resolved
New markets created
Weekly digest of open markets
Slack/email integration goes a long way for adoption.

What you can skip (vs. public markets)
Wallet/payment infrastructure
KYC/compliance
Withdrawal flows
Liquidity bootstrapping
Anti-manipulation systems
The trickiest part to get right is the market maker math and atomic trade execution — specifically making sure prices, balances, and positions stay consistent under concurrent trades. Everything else is fairly standard web development.

Want me to go deeper on any particular component?

yes, I am a mathematician and that is my jon

May 19
Great — so the market maker math is where you'll have the most fun and the most leverage. Let me go deep.

LMSR (Logarithmic Market Scoring Rule)
Invented by Robin Hanson. The cost function is:

C(q) = b · ln(Σ exp(qᵢ/b))

Where:

qᵢ = shares outstanding for outcome i
b = liquidity parameter (controls how much prices move per trade)
The price of outcome i is: pᵢ = exp(qᵢ/b) / Σ exp(qⱼ/b)
Notice the prices are just a softmax of the share quantities. The cost to move from state q to q' is simply C(q') - C(q).

Key properties:

Prices always sum to 1 (proper probability distribution)
Bounded loss for the market maker: worst case loss is b · ln(n) where n is the number of outcomes
Strictly proper scoring rule — truthful reporting is incentivized
The parameter b directly controls the subsidy and price sensitivity tradeoff
The problem: b is fixed at creation, so liquidity is static. Early trades move prices a lot, later trades less so relative to pool size. Also requires a subsidy upfront of b·ln(n).

CPMM (Constant Product Market Maker)
The Uniswap model applied to prediction markets. For a binary market, you maintain a pool:

x · y = k

Where x and y are shares of YES and NO outcomes. The price of YES is:

p(YES) = y / (x + y)

To buy Δ YES shares you solve: (x - Δ) · (y + cost) = k, so the cost in numeraire is:

cost = k/(x - Δ) - y

Key properties:

No upfront subsidy required — liquidity providers seed the pool
Price impact is endogenous — large trades move prices more
Simpler to implement than LMSR
Used by Manifold (with mana) and Polymarket
The problem: Prices don't naturally encode calibrated probabilities as cleanly — you need to think carefully about initialization. Also, liquidity providers take on risk.

Where it gets mathematically interesting
Calibration scoring — beyond just P&L, you can score users by the Brier score or log score of their trade history. This rewards accuracy not just profit, and is more meaningful for an internal forecasting tool.

Information aggregation — the theoretical question of how quickly market prices converge to the true probability given rational Bayesian traders. Connects to the efficient market hypothesis literature and Aumann's agreement theorem.

Subsidized liquidity — in LMSR, b is a free parameter. There's literature on adaptive b that adjusts based on trading volume, which solves the thin-market problem for internal tools with few users.

Multi-outcome markets — LMSR generalizes cleanly to n outcomes via the softmax formulation. CPMM requires more care (you need a multi-dimensional invariant surface).

Combinatorial markets — the really hard and interesting case. Markets over combinations of outcomes (e.g. "A wins AND B happens") where the outcome space is exponential. Hanson has a paper on combinatorial LMSR that's worth reading.

Practical recommendation for your use case
For an internal tool I'd implement LMSR because:

The bounded loss guarantee is useful when you control the subsidy budget
Calibration properties are cleaner theoretically
b gives you a single intuitive knob to tune market sensitivity
You're a mathematician — the elegance of the cost function is a feature
Start with binary markets, fix b per-market at creation, and add multi-outcome later once the core is solid.

Want to go into the resolution/payout math, the calibration scoring layer, or the numerical stability considerations for the LMSR implementation?

first, are these the only two options?

May 19
No, there are several others. Here's a broader landscape:

Other Market Mechanisms
Parimutuel Markets The classic horse-racing model. All bets go into a pool, and winners split it proportionally. No market maker needed — prices are determined by the distribution of bets at close. Simple to implement but prices are only final at resolution, which makes them poor for real-time probability estimation.

Order Book (CLOB) What Polymarket and Kalshi actually use in production. Buyers and sellers post limit orders, trades execute when they match. Gives the most accurate prices when there's enough liquidity, but requires many active traders to function well. Terrible for thin internal markets — you'll have wide spreads and no fills.

Quadratic Voting / Scoring Markets Users allocate a budget of points across outcomes, cost scales quadratically. Encourages spreading predictions rather than concentrating. More of a forecasting tool than a trading market.

Dynamic Parimutuel (DPM) A hybrid — parimutuel settlement but with real-time price signals during trading. Used by Inkling (one of the original corporate prediction market tools). Better than pure parimutuel for signaling but less principled than LMSR.

Fixed-Odds Markets A house sets the odds and takes the other side of every bet. Simple but requires manual odds-setting, which defeats the purpose of a forecasting market.

The Honest Landscape
Mechanism	Liquidity Needed	Price Quality	Complexity	Best For
LMSR	None (subsidized)	Very good	Medium	Internal/thin markets
CPMM	LP deposit	Good	Low	Crypto/community
Order Book	High	Best	High	Large liquid markets
Parimutuel	None	Poor (late)	Low	Simple pools
DPM	None	Moderate	Medium	Corporate tools
For your internal tool specifically
Order books are probably overkill unless you have hundreds of active traders. Parimutuel is too crude for real forecasting signal. That's why LMSR is the standard recommendation for internal markets — it works well precisely in the thin-liquidity regime you'll have.

That said, there's a fourth serious contender worth its own discussion: Scoring Rules without trading — where users just directly report probabilities and get scored, no market mechanism at all. Metaculus uses this model. It sidesteps the liquidity problem entirely and has very clean calibration properties.

Want to dig into any of these, or compare the scoring-rule approach vs. a proper trading market for your use case?

ok, so what is the dynamic b parameter for LMSR for thin markets you mentioned?

May 19
Good catch — I mentioned it in passing. Let me be precise about what's actually in the literature vs. what's engineering intuition, because it's worth being careful here.

The Problem with Fixed b
With fixed b, you face a fundamental tradeoff at market creation:

b too small — early trades move prices dramatically, discourages participation
b too large — subsidy cost is high (b·ln(n)), prices barely move even with strong signal
For internal markets with unpredictable participation, you don't know the right b in advance.

Othman et al. (2013) — Automated Market Makers that Learn
The main academic reference here is "Practical Liquidity-Sensitive Automated Market Making" by Othman, Pennock, Reeves, and Sandholm. The key idea:

Make b a function of trading volume:

b(q) = α · Σqᵢ

Where α is a fixed constant and Σqᵢ is total shares purchased so far. So b grows as volume grows — the market deepens endogenously as traders arrive.

The cost function becomes:

C(q) = b(q) · ln(Σ exp(qᵢ/b(q)))

But now b itself depends on q, so the cost to execute a trade is no longer just C(q') - C(q). You need to integrate the marginal cost along the path, which thankfully has a closed form in this model.

Key properties:

No fixed subsidy required upfront
Market maker loss is bounded by α · C(q) — proportional to volume, not fixed
Prices become less sensitive to individual trades as participation grows
Reduces to standard LMSR behavior in the high-volume limit
The Catch
The loss bound is now unbounded in absolute terms — it grows with volume. You're trading the fixed subsidy guarantee of LMSR for a volume-proportional one. For an internal tool where you control the stakes (play money), this is fine. For real money it requires more care.

Also the math gets harder — the integral for trade cost requires more careful numerical implementation.

A Simpler Engineering Approach
Honestly, for an internal tool many practitioners just use a heuristic adaptive b rather than the full Othman model:

Set an initial b₀ at market creation
After every k trades, recompute b based on observed volume or participation count
Treat it as a parameter you tune operationally rather than deriving theoretically
This loses the clean theoretical properties but is much simpler to implement and good enough in practice.

My honest assessment
If you want theoretical cleanliness, implement Othman et al. — the paper is readable and the math is tractable for a mathematician. If you want to ship something, start with fixed b, instrument how much prices move per trade, and adjust b at market creation based on expected participation. You can layer in dynamic b later.

Want to go through the Othman cost function derivation, or move on to numerical stability considerations for the LMSR implementation?

move on to numerical stability

May 19
Good — this is where a clean mathematical formulation can silently destroy you in production.

The Core Problem
The LMSR cost function is:

C(q) = b · ln(Σ exp(qᵢ/b))

The trade cost is C(q') - C(q). The problem is that exp(qᵢ/b) overflows float64 very quickly. As shares accumulate, qᵢ/b grows, and you're computing differences of astronomically large numbers.

The Log-Sum-Exp Trick
The standard fix is well-known in machine learning (it's the same problem as computing softmax stably). Factor out the maximum:

ln(Σ exp(xᵢ)) = m + ln(Σ exp(xᵢ - m))

Where m = max(xᵢ). Since xᵢ - m ≤ 0 for all i, the exp terms are all in (0, 1] — no overflow. And one term is exactly exp(0) = 1, so no underflow either.

So in practice you never compute the cost function directly. You always go through log-sum-exp.

The Subtler Problem: Catastrophic Cancellation
Even with log-sum-exp, computing the difference C(q') - C(q) is dangerous when the trade is small relative to existing volume. You're computing:

b · [LSE(q'/b) - LSE(q/b)]

When q' ≈ q, both LSE values are nearly equal and you lose significant digits in the subtraction. This is catastrophic cancellation — a classic numerical analysis problem.

The fix is to compute the difference directly rather than computing each term separately:

C(q') - C(q) = b · ln(Σ exp(qᵢ'/b)) - b · ln(Σ exp(qᵢ/b))

= b · ln(Σ exp(qᵢ'/b) / Σ exp(qᵢ/b))

Which you can rewrite as:

= b · ln(Σ pᵢ · exp((qᵢ' - qᵢ)/b))

Where pᵢ are the current prices (the softmax values). This is numerically much better because qᵢ' - qᵢ is small for small trades, and exp of a small number is well-conditioned.

Price Computation
Prices are:

pᵢ = exp(qᵢ/b) / Σ exp(qⱼ/b)

Never compute this directly. Always use:

pᵢ = exp(qᵢ/b - LSE(q/b))

Which is just the standard numerically stable softmax. This is safe for all practical share quantities.

Fixed Point Arithmetic
For a financial system you should also consider whether to use floating point at all. The risks:

Float arithmetic is not associative — trade costs can differ by tiny amounts depending on order of operations
Rounding errors accumulate over many trades
Two users executing the same sequence of trades may get slightly different balances
The standard solution is fixed point arithmetic — represent all quantities as integers with an implicit decimal scale (e.g. everything in units of 0.0001). This makes arithmetic exact and deterministic. Most production financial systems do this.

For an internal play-money tool floats are probably fine, but worth being aware of.

Atomicity
A separate but related concern — when a trade executes you need to update shares, prices, and balances atomically. If any step fails partway through you get an inconsistent state. This is a database transactions problem rather than numerical analysis, but it interacts with numerical stability: if you retry a failed transaction you must not apply partial updates.

Use database transactions with serializable isolation for all trade execution. This is non-negotiable.

Summary of What to Actually Implement
Always compute LSE via the max-shift trick
Compute trade costs as b·ln(Σ pᵢ·exp(Δqᵢ/b)) not as difference of two LSE calls
Use stable softmax for price queries
Decide early on fixed vs. floating point and be consistent
Wrap all trade execution in serializable transactions
The good news is that once you have a stable LSE implementation, everything else in LMSR is built on top of it cleanly. It's a one-time investment.

Want to move to the resolution and payout math, or the calibration scoring layer?

what is LSE?

May 19
Log-Sum-Exp — I started abbreviating it without flagging that I'd done so, sorry.

It's just the function:

LSE(x) = ln(Σ exp(xᵢ))

That's it. The name describes exactly what it computes: take the exponential of each element, sum them, take the log. It appears constantly in statistics and machine learning because it's the smooth maximum — as one xᵢ dominates the others, LSE(x) → max(xᵢ).

You've almost certainly seen it before under other names:

The log of the partition function in statistical mechanics
The log normalizer in exponential family distributions
The denominator computation in softmax
The numerical trick I described — subtracting the max before exponentiating — is just the standard way to evaluate it without overflow. It's sometimes called the "log-sum-exp trick" in ML literature but it's really just basic numerical analysis: factor out the dominant term to keep everything in a safe range.

So everywhere I wrote LSE(q/b), just read it as ln(Σ exp(qᵢ/b)).

let's look at the resolution and payout math

May 19
Resolution and Payout
This is actually the simpler part mathematically, but there are some interesting design decisions.

Basic Binary Resolution
When a market resolves, one outcome wins. The payout is straightforward:

payoutᵢ = sharesᵢ · R

Where R is the resolution value — 1.0 for the winning outcome, 0.0 for losing. So if you hold 47 YES shares and YES wins, you get 47 units of currency back.

This is clean because shares were always priced as probabilities in [0,1], so a resolved share is worth exactly 1 unit.

Where it Gets Interesting: Scalar Markets
Instead of YES/NO, the resolution is a continuous value in some range [min, max]. For example: "What will Q3 revenue be?" resolving to $4.2M against a range of $0-$10M.

The payout scales linearly:

R = (outcome - min) / (max - min)

So a share pays out proportionally to where the resolution falls in the range. This is elegant but introduces design questions:

Who sets min and max at creation?
What happens if resolution falls outside the range? You need to clamp or it breaks.
How do you handle disputes about the exact resolved value?
Multiple Choice Markets
N outcomes, exactly one wins. Each outcome has its own share pool. Resolution pays 1.0 to the winning outcome's shareholders, 0.0 to all others.

The subtlety here is what happens to the losing shares' value. In LMSR the market maker absorbed this — the subsidy covers the difference between what winners receive and what losers paid. You need to account for this in your subsidy budget tracking.

Ambiguous Resolution
This is the hard case and worth speccing carefully upfront. What happens when:

The event doesn't happen in the resolution window
The resolution criteria was poorly specified
There's genuine disagreement about the outcome
Your options:

Void the market — return all traders to their pre-trade balances. Clean but requires you to store the full trade history and reverse it, and is annoying for play-money systems.

N/A resolution — resolve at the current market price, so everyone gets back the market's implied probability times their shares. No one wins or loses relative to the final price. This is what Manifold does.

Admin discretion — a human decides. Simple but undermines trust if done arbitrarily. Needs a clear written policy.

For an internal tool I'd recommend N/A resolution plus a clear resolution criteria template that market creators must fill out. Bad resolution criteria is the most common failure mode in practice.

Payout Timing
Two models:

Immediate — resolve the market, compute payouts, credit balances atomically in one transaction. Simple, clean.

Redemption-based — resolution just marks shares as redeemable, users claim their payout explicitly. More complex but gives users an audit trail and lets them verify their payout before accepting it.

For an internal tool, immediate is fine.

The Accounting Identity
This is worth verifying in your implementation as an invariant:

Σ payouts to winners = Σ cost paid by all traders + initial subsidy

In a correctly implemented LMSR market, money is conserved. Every trade moves money from the market maker's subsidy into or out of trader balances. At resolution, the total paid out should equal total paid in plus the subsidy consumed.

If this identity doesn't hold in your system, you have a bug. Worth building an explicit invariant check that runs after every resolution.

What to Actually Store
For clean payout computation you need:

Every trade: user, outcome, shares purchased, cost paid, timestamp
Current share quantities per outcome per market
Current balance per user
Market state: open / closed / resolved / void
Resolution value and timestamp
Who resolved it and any notes
The trade log is your source of truth. Balances and share quantities are derived from it. In a well-designed system you should be able to recompute the entire current state by replaying the trade log from scratch — useful for debugging and auditing.

Want to move to the calibration scoring layer next? That's where it gets mathematically rich again.

ok

May 19
Calibration Scoring
This is arguably the most mathematically interesting part for an internal forecasting tool, and the part most prediction market implementations underinvest in.

Why P&L Alone is Insufficient
Profit and loss is a noisy signal of forecasting skill:

A trader who bets big on a 90% favorite and wins looks brilliant
A trader who correctly identifies a 30% event as 30% makes no money but is perfectly calibrated
Luck dominates skill over short horizons
You want to measure calibration — does a trader's stated probability match the actual frequency of outcomes? If someone says 70% on 100 markets, did roughly 70 of them resolve YES?

Proper Scoring Rules
A scoring rule assigns a score to a probability forecast after resolution. It is proper if the optimal strategy is to report your true beliefs — no incentive to shade.

The two canonical ones:

Brier Score
BS = (p - o)²

Where p is the forecast probability and o is the outcome (1 or 0). Lower is better. Ranges from 0 (perfect) to 1 (maximally wrong).

Simple, interpretable, quadratic penalty for being wrong. The population average Brier score for a forecaster tells you their overall accuracy.

Log Score
LS = o · ln(p) + (1 - o) · ln(1 - p)

Higher is better (less negative). This is the log likelihood of the outcome under your forecast. Penalizes extreme miscalibration much more harshly than Brier — saying 1% on something that happens costs you enormously.

Log score connects directly to information theory — it measures how many bits of information the forecaster contributed.

Which to Use
For an internal tool I'd recommend Brier score for display because it's intuitive to non-mathematicians, but compute both internally. They tell you slightly different things:

Brier score is more forgiving of moderate miscalibration
Log score is more sensitive to overconfident extreme forecasts
They can disagree on ranking forecasters
Decomposition
The Brier score has a beautiful decomposition due to Murphy (1973):

BS = Reliability - Resolution + Uncertainty

Where:

Reliability — how close your stated probabilities are to observed frequencies (lower is better, 0 is perfect)
Resolution — how much your forecasts differ from the base rate (higher is better — you're adding information)
Uncertainty — the base rate variance, a constant for a given set of markets
This decomposition is extremely useful for diagnosing forecaster behavior:

High reliability, low resolution → you're well calibrated but not saying anything bold
Low reliability, high resolution → you're making bold calls but they're miscalibrated
Both good → you're a skilled forecaster
Calibration Curves
Beyond a single number, you want to plot the calibration curve:

Bin all forecasts by stated probability (0-10%, 10-20%, ..., 90-100%)
For each bin, compute the actual resolution frequency
Plot stated vs. actual
A perfectly calibrated forecaster lies on the diagonal. Systematic deviation tells you:

Above diagonal — underconfident (says 40%, things happen 60% of the time)
Below diagonal — overconfident (says 70%, things happen 50% of the time)
This is one of the most useful displays you can build for an internal tool — people find it genuinely surprising and informative about their own thinking.

Scoring Trades vs. Positions
There's a subtlety in how you assign scores in a trading market vs. a direct forecasting system:

Direct reporting (Metaculus style) — user states a probability at a point in time, gets scored on that probability at resolution. Clean.

Trading market — user's implied probability is inferred from their trades. What probability do you score them on? Options:

Score on the price at which they traded (their revealed belief at trade time)
Score on their final portfolio-implied probability
Score on a time-weighted average of their positions
Each has different incentive properties. Scoring on trade price is simplest and most defensible — it directly measures whether they thought the market was mispriced at the moment they acted.

Practical Leaderboard Design
For an internal tool, surface these metrics per user:

Total markets participated in — sample size matters
Brier score — headline accuracy number
Reliability — are you well calibrated
Resolution — are you adding information beyond the base rate
Calibration curve — visual
P&L — still useful as a complementary signal
Weight the leaderboard by participation count — a single lucky correct forecast on one market shouldn't rank someone above someone with 50 well-calibrated forecasts.

The Deeper Connection
For a mathematician, it's worth noting that proper scoring rules, the LMSR cost function, and Bayesian updating are all deeply connected:

The log score is the natural scoring rule for Bayesian forecasters
LMSR is equivalent to a market where each trader is a Bayesian agent updating a shared prior
The market price at any point is the geometric mean of trader beliefs under log scoring
This isn't just aesthetically pleasing — it means your market mechanism and your scoring layer are measuring the same underlying thing from different angles. A well-designed system makes this connection explicit.

Want to go into the leaderboard and UI layer, or talk about how to structure the database schema to make all this scoring computation efficient?

database schema

May 19
Database Schema
Let me go through this table by table, with the reasoning behind each design decision.

Core Tables
Users
sql
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id   TEXT UNIQUE NOT NULL,  -- your SSO identifier
    display_name  TEXT NOT NULL,
    email         TEXT UNIQUE NOT NULL,
    balance       NUMERIC(20, 8) NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
external_id is whatever your SSO system provides — don't generate your own auth identifiers. NUMERIC(20,8) gives you fixed point arithmetic — 8 decimal places, no floating point errors.

Markets
sql
CREATE TABLE markets (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id          UUID NOT NULL REFERENCES users(id),
    title               TEXT NOT NULL,
    description         TEXT NOT NULL,
    resolution_criteria TEXT NOT NULL,  -- explicit, required
    market_type         TEXT NOT NULL,  -- 'binary', 'scalar', 'multiple_choice'
    status              TEXT NOT NULL DEFAULT 'open',
                        -- 'open', 'closed', 'resolved', 'void'
    b                   NUMERIC(20, 8) NOT NULL,  -- LMSR liquidity parameter
    subsidy             NUMERIC(20, 8) NOT NULL,  -- initial market maker stake
    close_at            TIMESTAMPTZ NOT NULL,
    resolved_at         TIMESTAMPTZ,
    resolver_id         UUID REFERENCES users(id),
    resolution_value    NUMERIC(20, 8),  -- NULL until resolved
    resolution_notes    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT valid_status CHECK (
        status IN ('open', 'closed', 'resolved', 'void')
    ),
    CONSTRAINT valid_type CHECK (
        market_type IN ('binary', 'scalar', 'multiple_choice')
    )
);
resolution_criteria is a required field — enforced at the schema level. resolution_value is NULL until resolution, then stores 0.0/1.0 for binary, the scalar value, or the winning outcome index.

Outcomes
sql
CREATE TABLE outcomes (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    market_id    UUID NOT NULL REFERENCES markets(id),
    label        TEXT NOT NULL,  -- 'YES'/'NO', or 'Candidate A', etc.
    index        INTEGER NOT NULL,  -- ordering within market
    shares_out   NUMERIC(20, 8) NOT NULL DEFAULT 0,  -- qᵢ in LMSR notation
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (market_id, index)
);
shares_out is your qᵢ — the total shares outstanding for this outcome. This is the live state the market maker reads to compute prices. For binary markets you'll always have exactly two rows per market.

Trades
sql
CREATE TABLE trades (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    market_id       UUID NOT NULL REFERENCES markets(id),
    user_id         UUID NOT NULL REFERENCES users(id),
    outcome_id      UUID NOT NULL REFERENCES outcomes(id),
    shares          NUMERIC(20, 8) NOT NULL,  -- positive = buy, negative = sell
    cost            NUMERIC(20, 8) NOT NULL,  -- positive = spent, negative = received
    price_before    NUMERIC(20, 8) NOT NULL,  -- implied prob before trade
    price_after     NUMERIC(20, 8) NOT NULL,  -- implied prob after trade
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
This is your immutable audit log. Never update or delete rows here. price_before and price_after are denormalized for convenience — you could recompute them from shares_out history but it's expensive. Storing them makes calibration scoring and charting cheap.

Positions
sql
CREATE TABLE positions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id),
    market_id   UUID NOT NULL REFERENCES markets(id),
    outcome_id  UUID NOT NULL REFERENCES outcomes(id),
    shares      NUMERIC(20, 8) NOT NULL DEFAULT 0,

    UNIQUE (user_id, outcome_id)
);
This is a materialized view of the trade log — derived state, not source of truth. Every trade updates this atomically alongside inserting into trades. Makes portfolio queries fast without scanning the full trade history.

Payouts
sql
CREATE TABLE payouts (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    market_id    UUID NOT NULL REFERENCES markets(id),
    user_id      UUID NOT NULL REFERENCES users(id),
    amount       NUMERIC(20, 8) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (market_id, user_id)  -- one payout per user per market
);
Written atomically at resolution time. The unique constraint prevents double payouts.

Scores
sql
CREATE TABLE scores (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    market_id       UUID NOT NULL REFERENCES markets(id),
    user_id         UUID NOT NULL REFERENCES users(id),
    trade_id        UUID NOT NULL REFERENCES trades(id),
    forecast_prob   NUMERIC(20, 8) NOT NULL,  -- price_after at trade time
    outcome         NUMERIC(20, 8),           -- NULL until resolved
    brier_score     NUMERIC(20, 8),           -- NULL until resolved
    log_score       NUMERIC(20, 8),           -- NULL until resolved
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
One row per trade. forecast_prob is the price after the trade — the trader's revealed belief. Scores are NULL until the market resolves, then filled in by the resolution job.

The Critical Invariant: Accounting
Add a view that checks your accounting identity:

sql
CREATE VIEW market_accounting AS
SELECT
    m.id,
    m.subsidy,
    COALESCE(SUM(t.cost), 0)        AS total_traded_in,
    COALESCE(SUM(p.amount), 0)      AS total_paid_out,
    m.subsidy
        + COALESCE(SUM(t.cost), 0)
        - COALESCE(SUM(p.amount), 0) AS remainder
FROM markets m
LEFT JOIN trades t ON t.market_id = m.id
LEFT JOIN payouts p ON p.market_id = m.id
GROUP BY m.id, m.subsidy;
remainder should be zero (or very small due to rounding) after resolution. If it's not, you have a bug. Run this check after every resolution.

Indexes
sql
-- Trade history per market (price chart, volume)
CREATE INDEX idx_trades_market_time
    ON trades(market_id, created_at);

-- Portfolio per user
CREATE INDEX idx_positions_user
    ON positions(user_id);

-- Scoring queries per user
CREATE INDEX idx_scores_user
    ON scores(user_id);

-- Open markets (home page query)
CREATE INDEX idx_markets_status_close
    ON markets(status, close_at)
    WHERE status = 'open';
Transaction Pattern for Trade Execution
Every trade must do all of this atomically:

sql
BEGIN;

-- 1. Lock the market row (prevents concurrent trades racing)
SELECT id, status, b FROM markets
    WHERE id = $market_id FOR UPDATE;

-- 2. Lock the relevant outcome rows
SELECT id, shares_out FROM outcomes
    WHERE market_id = $market_id FOR UPDATE;

-- 3. Compute cost (in application layer using LMSR math)

-- 4. Insert trade record
INSERT INTO trades (...) VALUES (...);

-- 5. Update outcome shares
UPDATE outcomes SET shares_out = shares_out + $delta
    WHERE id = $outcome_id;

-- 6. Update or insert position
INSERT INTO positions (user_id, market_id, outcome_id, shares)
    VALUES ($user_id, $market_id, $outcome_id, $shares)
ON CONFLICT (user_id, outcome_id)
    DO UPDATE SET shares = positions.shares + EXCLUDED.shares;

-- 7. Deduct user balance
UPDATE users SET balance = balance - $cost
    WHERE id = $user_id;

-- 8. Insert score row (outcome and scores NULL for now)
INSERT INTO scores (market_id, user_id, trade_id, forecast_prob)
    VALUES ($market_id, $user_id, $trade_id, $price_after);

COMMIT;
The FOR UPDATE locks on markets and outcomes are essential — they serialize concurrent trades on the same market so your LMSR state never gets corrupted by a race condition.

Key Design Principles Applied
Trades table is immutable — append only, never update
Positions is derived state — always recomputable from trades
All money is NUMERIC — no floats anywhere near balances
Accounting identity is a view — always queryable, not a one-time check
Resolution is a transaction — payouts and score fills happen atomically
Want to go into the API layer next, or the resolution job specifically?


