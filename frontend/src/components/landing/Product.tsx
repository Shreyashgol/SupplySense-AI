import React from 'react';

export const Product: React.FC = () => {
  return (
    <section id="product" className="py-32 px-6 max-w-5xl mx-auto">
      <div className="mb-20 text-center">
        <span className="text-xs font-bold uppercase tracking-widest text-[#6b6b6b] mb-4 block">
          Product
        </span>
        <h2 className="text-4xl md:text-5xl font-bold tracking-tight text-[#1a1a1a]">
          Built for operational clarity
        </h2>
      </div>

      <div className="grid md:grid-cols-3 gap-8">
        <div className="bg-white p-10 rounded-2xl border border-black/5 flex flex-col items-start transition-transform hover:-translate-y-1 duration-300">
          <div className="bg-[#f4f4f2] p-4 rounded-xl mb-6">
            <svg className="w-8 h-8 text-[#1a1a1a]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h3 className="text-xl font-bold text-[#1a1a1a] mb-4">Real-time Risk Detection</h3>
          <p className="text-[#6b6b6b] leading-relaxed">
            Monitor events across your entire supply chain and instantly flag risks before they escalate into major disruptions.
          </p>
        </div>

        <div className="bg-white p-10 rounded-2xl border border-black/5 flex flex-col items-start transition-transform hover:-translate-y-1 duration-300">
          <div className="bg-[#f4f4f2] p-4 rounded-xl mb-6">
            <svg className="w-8 h-8 text-[#1a1a1a]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          </div>
          <h3 className="text-xl font-bold text-[#1a1a1a] mb-4">Executive Action Plans</h3>
          <p className="text-[#6b6b6b] leading-relaxed">
            Don't just detect problems. Our AI generates concrete, prioritized action plans from live decision runs.
          </p>
        </div>

        <div className="bg-white p-10 rounded-2xl border border-black/5 flex flex-col items-start transition-transform hover:-translate-y-1 duration-300">
          <div className="bg-[#f4f4f2] p-4 rounded-xl mb-6">
            <svg className="w-8 h-8 text-[#1a1a1a]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 7v8a2 2 0 002 2h6M8 7V5a2 2 0 012-2h4.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V15a2 2 0 01-2 2h-2M8 7H6a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2v-2" />
            </svg>
          </div>
          <h3 className="text-xl font-bold text-[#1a1a1a] mb-4">Scenario Simulation</h3>
          <p className="text-[#6b6b6b] leading-relaxed">
            Test and compare "what-if" outcomes side-by-side before committing resources to any specific response strategy.
          </p>
        </div>
      </div>
    </section>
  );
};
