import React, { useState } from 'react';

export const Contact: React.FC = () => {
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setStatus('loading');
    
    const form = e.currentTarget;
    const data = new FormData(form);

    try {
      const response = await fetch('https://formspree.io/f/YOUR_ENDPOINT_ID', {
        method: 'POST',
        body: data,
        headers: {
          'Accept': 'application/json'
        }
      });
      
      if (response.ok) {
        setStatus('success');
        form.reset();
      } else {
        setStatus('error');
      }
    } catch (error) {
      setStatus('error');
    }
  };

  return (
    <section id="contact" className="py-32 px-6 max-w-2xl mx-auto">
      <div className="text-center mb-16">
        <h2 className="text-4xl md:text-5xl font-bold tracking-tight text-[#1a1a1a] mb-6">
          Get in touch
        </h2>
        <p className="text-lg text-[#6b6b6b]">
          Have a question or want a walkthrough? Send us a message.
        </p>
      </div>

      <div className="bg-white p-8 md:p-12 rounded-2xl border border-black/5 shadow-sm">
        {status === 'success' ? (
          <div className="text-center py-8">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-[#f4f4f2] mb-6">
              <svg className="w-8 h-8 text-[#1a1a1a]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h3 className="text-2xl font-bold text-[#1a1a1a] mb-2">Message sent successfully</h3>
            <p className="text-[#6b6b6b]">We'll get back to you soon.</p>
            <button 
              onClick={() => setStatus('idle')}
              className="mt-8 text-[#1a1a1a] hover:text-[#6b6b6b] font-medium transition-colors"
            >
              Send another message
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-6">
            {status === 'error' && (
              <div className="p-4 bg-red-50 text-red-600 rounded-lg text-sm mb-6 border border-red-100">
                There was a problem sending your message. Please try again.
              </div>
            )}
            
            <div>
              <label htmlFor="name" className="block text-sm font-medium text-[#1a1a1a] mb-2">Name</label>
              <input 
                type="text" 
                id="name" 
                name="name" 
                required 
                className="w-full px-4 py-3 bg-[#f4f4f2] border border-transparent focus:border-black/10 focus:bg-white rounded-lg outline-none transition-colors"
                placeholder="Jane Doe"
              />
            </div>
            
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-[#1a1a1a] mb-2">Email</label>
              <input 
                type="email" 
                id="email" 
                name="email" 
                required 
                className="w-full px-4 py-3 bg-[#f4f4f2] border border-transparent focus:border-black/10 focus:bg-white rounded-lg outline-none transition-colors"
                placeholder="jane@example.com"
              />
            </div>
            
            <div>
              <label htmlFor="message" className="block text-sm font-medium text-[#1a1a1a] mb-2">Message</label>
              <textarea 
                id="message" 
                name="message" 
                required 
                rows={5}
                className="w-full px-4 py-3 bg-[#f4f4f2] border border-transparent focus:border-black/10 focus:bg-white rounded-lg outline-none transition-colors resize-none"
                placeholder="How can we help you?"
              ></textarea>
            </div>
            
            <button 
              type="submit" 
              disabled={status === 'loading'}
              className="w-full bg-[#1a1a1a] hover:bg-black text-white px-8 py-4 rounded-xl text-lg font-medium transition-colors disabled:opacity-70 disabled:cursor-not-allowed flex items-center justify-center"
            >
              {status === 'loading' ? (
                <>
                  <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Sending...
                </>
              ) : (
                'Send message'
              )}
            </button>
            <input type="hidden" name="_to" value="golhanishreyash@gmail.com" />
          </form>
        )}
      </div>
    </section>
  );
};
