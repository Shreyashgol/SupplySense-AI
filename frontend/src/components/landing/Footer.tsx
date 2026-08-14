import React from 'react';

export const Footer: React.FC = () => {
  return (
    <footer className="border-t border-black/5 bg-white pt-20 pb-10 px-6">
      <div className="max-w-5xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-12 mb-16">
        <div>
          <span className="font-bold text-xl tracking-tight text-[#1a1a1a] mb-2 block">SupplySense-AI</span>
          <p className="text-[#6b6b6b]">Turning supply chain data into intelligent action.</p>
        </div>
        
        <div>
          <h4 className="font-bold text-[#1a1a1a] mb-6">Company</h4>
          <ul className="space-y-4 text-[#6b6b6b]">
            <li><a href="#about" className="hover:text-[#1a1a1a] transition-colors">About us</a></li>
            <li><a href="#product" className="hover:text-[#1a1a1a] transition-colors">Product</a></li>
            <li><a href="#contact" className="hover:text-[#1a1a1a] transition-colors">Contact us</a></li>
          </ul>
        </div>
        
        <div>
          <h4 className="font-bold text-[#1a1a1a] mb-6">Capabilities</h4>
          <ul className="space-y-4 text-[#6b6b6b]">
            <li>Real-time Risk Detection & Alerts</li>
            <li>AI Scenario Simulation & Comparison</li>
            <li>Executive Action Plan Generation</li>
            <li>Detection Accuracy Tracking</li>
          </ul>
        </div>
      </div>
      
      <div className="max-w-5xl mx-auto pt-8 border-t border-black/5 text-sm text-[#6b6b6b] flex flex-col md:flex-row justify-between items-center">
        <p>© 2026 SupplySense-AI. All rights reserved.</p>
      </div>
    </footer>
  );
};
