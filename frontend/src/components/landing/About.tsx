import React from 'react';

export const About: React.FC = () => {
  return (
    <section id="about" className="py-32 px-6 max-w-4xl mx-auto text-center">
      <div className="mb-12">
        <span className="text-xs font-bold uppercase tracking-widest text-[#6b6b6b] mb-4 block">
          About us
        </span>
        <h2 className="text-4xl md:text-5xl font-bold tracking-tight text-[#1a1a1a]">
          Turning supply chain data into intelligent action.
        </h2>
      </div>
      
      <p className="text-xl text-[#6b6b6b] leading-relaxed max-w-3xl mx-auto">
        Every supply chain generates data — shipments, orders, risk signals, compliance checks. Very little of it becomes a decision anyone can act on in time. 
        <br /><br />
        <strong className="text-[#1a1a1a] font-medium">SupplySense-AI closes that gap:</strong> it watches your operations continuously, flags risk before it becomes disruption, simulates the outcome of different responses, and turns all of it into a clear, executive-ready action plan. 
        <br /><br />
        We're building the layer between raw operational data and the decisions your team actually needs to make — faster, and with more confidence.
      </p>
    </section>
  );
};
