"use client";

import { useState } from "react";
import { UploadCloud, Search, Database, Settings2, FileText, ChevronRight, CheckCircle2, Loader2, Sparkles } from "lucide-react";

/** Base URL for the Search Agent backend API (configured via .env.local). */
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [chunkSize, setChunkSize] = useState(1000);
  const [chunkOverlap, setChunkOverlap] = useState(200);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<any[]>([]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setUploadStatus(null);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setIsUploading(true);
    setUploadStatus(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("chunk_size", chunkSize.toString());
    formData.append("chunk_overlap", chunkOverlap.toString());

    try {
      const res = await fetch(`${API_URL}/api/v1/ingest`, {
        method: "POST",
        body: formData,
      });
      if (res.ok) {
        setUploadStatus("Success");
      } else {
        setUploadStatus("Failed");
      }
    } catch (err) {
      console.error(err);
      setUploadStatus("Error");
    } finally {
      setIsUploading(false);
      setTimeout(() => setUploadStatus(null), 3000);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setIsSearching(true);
    setSearchResults([]);

    try {
      const res = await fetch(`${API_URL}/api/v1/search`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query, limit: 5 }),
      });
      if (res.ok) {
        const data = await res.json();
        setSearchResults(data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <main className="min-h-screen p-6 md:p-12 lg:p-24 relative overflow-hidden">
      {/* Decorative background gradients are handled in globals.css */}

      <div className="max-w-6xl mx-auto relative z-10 animate-fade-in">
        <header className="mb-16 text-center space-y-4">
          <div className="inline-flex items-center justify-center p-3 rounded-full glass-panel mb-4 shadow-lg">
            <Sparkles className="w-6 h-6 text-blue-400 mr-2" />
            <h1 className="text-2xl font-bold text-gradient tracking-wide">Multi-Agent Knowledge Base</h1>
          </div>
          <p className="text-slate-400 max-w-2xl mx-auto text-lg">
            Ingest multimodal documents into your hybrid vector search network.
            Adjust processing vectors and explore the agent semantic space.
          </p>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">

          {/* Left Column - Ingestion */}
          <div className="lg:col-span-4 space-y-6 animate-fade-in-delayed">
            <div className="glass-panel rounded-2xl p-6 transition-all hover:border-blue-500/30">
              <div className="flex items-center mb-6 border-b border-slate-700/50 pb-4">
                <Database className="w-5 h-5 text-blue-400 mr-3" />
                <h2 className="text-xl font-semibold text-slate-100">Ingestion Config</h2>
              </div>

              <div className="space-y-6">
                <div>
                  <div className="flex justify-between text-sm mb-2 text-slate-300">
                    <label className="flex items-center"><Settings2 className="w-4 h-4 mr-2" /> Chunk Size</label>
                    <span className="text-blue-400 font-mono bg-blue-500/10 px-2 py-0.5 rounded">{chunkSize}</span>
                  </div>
                  <input
                    type="range"
                    min="100" max="2000" step="100"
                    value={chunkSize}
                    onChange={(e) => setChunkSize(parseInt(e.target.value))}
                    className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
                  />
                </div>

                <div>
                  <div className="flex justify-between text-sm mb-2 text-slate-300">
                    <label className="flex items-center"><Settings2 className="w-4 h-4 mr-2" /> Chunk Overlap</label>
                    <span className="text-purple-400 font-mono bg-purple-500/10 px-2 py-0.5 rounded">{chunkOverlap}</span>
                  </div>
                  <input
                    type="range"
                    min="0" max="500" step="50"
                    value={chunkOverlap}
                    onChange={(e) => setChunkOverlap(parseInt(e.target.value))}
                    className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
                  />
                </div>

                <div className="pt-4 mt-4 border-t border-slate-700/50">
                  <label className="block w-full cursor-pointer">
                    <div className={`border-2 border-dashed rounded-xl p-8 text-center transition-all duration-300 ${file ? 'border-blue-500/50 bg-blue-500/5' : 'border-slate-600 hover:border-blue-400 hover:bg-slate-800/50'}`}>
                      <UploadCloud className={`w-10 h-10 mx-auto mb-3 ${file ? 'text-blue-400' : 'text-slate-400'}`} />
                      <span className="text-sm font-medium text-slate-300">
                        {file ? file.name : 'Select file to upload'}
                      </span>
                      <input type="file" className="hidden" onChange={handleFileChange} />
                    </div>
                  </label>
                </div>

                <button
                  onClick={handleUpload}
                  disabled={!file || isUploading}
                  className="w-full py-3 px-4 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 disabled:from-slate-700 disabled:to-slate-700 disabled:text-slate-500 text-white font-medium rounded-xl shadow-lg transition-all transform active:scale-[0.98] flex justify-center items-center hover-glow"
                >
                  {isUploading ? (
                    <><Loader2 className="w-5 h-5 mr-2 animate-spin" /> Ingesting...</>
                  ) : uploadStatus === "Success" ? (
                    <><CheckCircle2 className="w-5 h-5 mr-2 text-green-400" /> Successful</>
                  ) : (
                    'Ingest Document'
                  )}
                </button>
              </div>
            </div>
          </div>

          {/* Right Column - Search & Results */}
          <div className="lg:col-span-8 space-y-6 animate-fade-in-delayed" style={{ animationDelay: '0.3s' }}>
            <div className="glass-panel rounded-2xl p-6">
              <form onSubmit={handleSearch} className="mb-8">
                <div className="relative input-focus-ring rounded-xl transition-all">
                  <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                    <Search className="h-5 w-5 text-slate-400" />
                  </div>
                  <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Search through knowledge space (semantic + hybrid)..."
                    className="w-full bg-slate-900/50 border border-slate-700 rounded-xl py-4 pl-12 pr-32 text-slate-100 placeholder-slate-500 focus:outline-none"
                  />
                  <button
                    type="submit"
                    disabled={!query.trim() || isSearching}
                    className="absolute right-2 top-2 bottom-2 px-6 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium transition-colors flex items-center disabled:bg-slate-700"
                  >
                    {isSearching ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Search'}
                  </button>
                </div>
              </form>

              <div className="space-y-4 min-h-[400px]">
                {searchResults.length === 0 && !isSearching && (
                  <div className="h-[300px] flex flex-col items-center justify-center text-slate-500 border border-dashed border-slate-700 rounded-xl bg-slate-800/20">
                    <FileText className="w-12 h-12 mb-4 opacity-50" />
                    <p>Enter a query to explore the vector space</p>
                  </div>
                )}

                {searchResults.map((result, idx) => (
                  <div
                    key={idx}
                    className="bg-slate-800/40 border border-slate-700/50 hover:border-blue-500/30 p-5 rounded-xl transition-all duration-300 hover:shadow-lg hover:-translate-y-1"
                    style={{ animation: `fadeIn 0.3s ease-out ${idx * 0.1}s forwards`, opacity: 0 }}
                  >
                    <div className="flex justify-between items-start mb-3">
                      <div className="flex items-center space-x-2">
                        <span className="bg-blue-500/20 text-blue-300 text-xs font-mono px-2 py-1 rounded">
                          Score: {(result.score).toFixed(4)}
                        </span>
                        <span className="bg-purple-500/20 text-purple-300 text-xs font-mono px-2 py-1 rounded flex items-center">
                          <Database className="w-3 h-3 mr-1" /> {result.metadata.source || 'Unknown Source'}
                        </span>
                      </div>
                      <ChevronRight className="w-4 h-4 text-slate-500" />
                    </div>
                    <p className="text-slate-300 leading-relaxed text-sm">
                      {result.content}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>

        </div>
      </div>
    </main>
  );
}
