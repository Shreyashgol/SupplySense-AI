import React from 'react';

interface NavbarProps {
  onLaunch: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ onLaunch }) => {
  return (
    <nav className="sticky top-0 z-50 bg-[#f4f4f2]/90 backdrop-blur-md border-b border-black/5 px-6 py-4 flex items-center justify-between transition-all duration-300">
      <div className="flex items-center gap-2">
        <span className="font-bold text-xl tracking-tight text-[#1a1a1a]">SupplySense-AI</span>
      </div>
      
      <div className="hidden md:flex items-center gap-8 text-sm font-medium tracking-wide uppercase text-[#6b6b6b]">
        <a href="#about" className="hover:text-[#1a1a1a] transition-colors">About us</a>
        <a href="#product" className="hover:text-[#1a1a1a] transition-colors">Product</a>
        <a href="#contact" className="hover:text-[#1a1a1a] transition-colors">Contact us</a>
      </div>

      <button 
        onClick={onLaunch}
        className="bg-[#1a1a1a] hover:bg-black text-white px-5 py-2.5 rounded-full text-sm font-medium transition-colors shadow-sm"
      >
        Launch app
      </button>
    </nav>
  );
};
