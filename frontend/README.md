This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

This is the **professional separate frontend** for the LMSR simulator (completely independent of the Streamlit demo in the parent project).

## Running the full professional stack

See the root `README.md` ("Professional Separate Frontend + Backend" section) and `examples/README.md` for complete instructions.

The easiest way:

```bash
# From the project root (parent of this frontend/ directory)
chmod +x start-professional-ui.sh
./start-professional-ui.sh
```

Then in another terminal:
```bash
cd frontend
npm run dev
```

Open http://localhost:3000.

- Use the top user dropdown to switch between the 300-round bot users and see exactly what each user sees (cash, position value/MTM, total equity, their positions, trade as them).
- Admin tab: global activity + resolve controls + **Demo Scenarios** chooser (dropdown of every demo from the Streamlit app + Load/Reset buttons that swap the entire DB state).

**Prerequisites (from project root)**
- Python venv + `pip install -e ".[api]"`
- The 300-round seeder (`python examples/ui_300_round_bots.py`) to populate many realistic users instead of just "demo_bot".
- Backend running (`lmsr serve` or `uvicorn lmsr.api:app --port 8000`).
- Node.js + npm (for this frontend).

## Getting Started (frontend only)

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

For project-specific details (bot logic, the 300-round demo with true p≈0.8, admin backend endpoints, etc.) see the root `README.md` and `examples/README.md`.

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
